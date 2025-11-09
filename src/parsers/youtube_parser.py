import logging
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup  # type: ignore

from parsers.utils_extract import (
    extract_emails,
    extract_phones,
    choose_best_email_for_domains,
)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

@dataclass
class ChannelContact:
    Channel_url: str
    Channel_name: str
    Email: str
    Domain_email: str
    Phone: str
    Description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class YouTubeScraper:
    """
    Scraper that uses the YouTube Data API v3 and HTML parsing
    to extract emails and phone numbers from channel info.
    """

    def __init__(
        self,
        api_key: str,
        logger: Optional[logging.Logger] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key:
            raise ValueError("YouTubeScraper requires a non-empty API key.")
        self.api_key = api_key
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def scrape_contacts(
        self,
        keyword: str,
        max_results: int = 50,
        domain_whitelist: Optional[List[str]] = None,
    ) -> List[ChannelContact]:
        channel_ids = list(
            self._search_channels(keyword=keyword, max_results=max_results)
        )
        self.logger.info("Found %d channel candidates.", len(channel_ids))

        if not channel_ids:
            return []

        channel_details = self._get_channel_details(channel_ids)
        contacts: List[ChannelContact] = []

        for detail in channel_details:
            try:
                contact = self._extract_contact_from_channel_data(
                    detail, domain_whitelist=domain_whitelist
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to extract contacts for channel %s: %s",
                    detail.get("id"),
                    exc,
                )
                continue

            if contact is None:
                continue

            contacts.append(contact)

        return contacts

    def _search_channels(
        self,
        keyword: str,
        max_results: int,
    ) -> Iterable[str]:
        """
        Use YouTube Data API search endpoint to get channel IDs for a keyword.
        Handles pagination up to max_results.
        """
        if max_results <= 0:
            return []

        remaining = max_results
        page_token: Optional[str] = None

        while remaining > 0:
            batch = min(50, remaining)
            params = {
                "key": self.api_key,
                "q": keyword,
                "type": "channel",
                "part": "snippet",
                "maxResults": batch,
            }
            if page_token:
                params["pageToken"] = page_token

            self.logger.debug(
                "Requesting YouTube search with params: %s", params
            )
            try:
                resp = self.session.get(YOUTUBE_SEARCH_URL, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.logger.error("Search request failed: %s", exc)
                break

            data = resp.json()
            items = data.get("items", [])
            for item in items:
                kind = (
                    item.get("id", {}).get("kind", "")
                    if isinstance(item.get("id"), dict)
                    else ""
                )
                if not kind.endswith("#channel"):
                    continue
                channel_id = item.get("id", {}).get("channelId")
                if channel_id:
                    yield channel_id
                    remaining -= 1
                    if remaining == 0:
                        break

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    def _get_channel_details(self, channel_ids: List[str]) -> List[dict]:
        """
        Fetch channel details including description and custom URLs.
        Uses the channels endpoint in batches.
        """
        if not channel_ids:
            return []

        details: List[dict] = []
        step = 50

        for i in range(0, len(channel_ids), step):
            batch_ids = channel_ids[i : i + step]
            params = {
                "key": self.api_key,
                "id": ",".join(batch_ids),
                "part": "snippet,brandingSettings",
                "maxResults": len(batch_ids),
            }
            self.logger.debug(
                "Requesting YouTube channels info for %d ids", len(batch_ids)
            )
            try:
                resp = self.session.get(YOUTUBE_CHANNELS_URL, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.logger.error("Channel details request failed: %s", exc)
                continue

            data = resp.json()
            items = data.get("items", [])
            details.extend(items)

        return details

    def _build_channel_url(self, channel_data: dict) -> str:
        cid = channel_data.get("id", "")
        if not cid:
            return ""
        return f"https://www.youtube.com/channel/{cid}"

    def _fetch_about_html(self, channel_url: str) -> str:
        """
        Best-effort fetch of the channel's About page HTML.
        Failure here does not stop processing; returns empty string on error.
        """
        if not channel_url:
            return ""

        about_url = channel_url.rstrip("/") + "/about"
        self.logger.debug("Fetching channel about page: %s", about_url)
        try:
            resp = self.session.get(about_url, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            self.logger.info(
                "Failed to fetch about page for %s: %s", channel_url, exc
            )
            return ""

    def _extract_contact_from_channel_data(
        self,
        channel_data: dict,
        domain_whitelist: Optional[List[str]] = None,
    ) -> Optional[ChannelContact]:
        snippet = channel_data.get("snippet") or {}
        channel_name = snippet.get("title", "").strip()
        description = snippet.get("description", "").strip()

        channel_url = self._build_channel_url(channel_data)
        html = self._fetch_about_html(channel_url)

        text_blobs: List[str] = [description]
        if html:
            soup = BeautifulSoup(html, "html.parser")
            text_blobs.append(soup.get_text(" ", strip=True))

        combined_text = "\n".join(text_blobs)

        emails = extract_emails(combined_text)
        phones = extract_phones(combined_text)

        primary_email, primary_domain = choose_best_email_for_domains(
            emails, domain_whitelist
        )

        if domain_whitelist and not primary_email:
            # Skip channels that do not match the whitelist at all
            self.logger.debug(
                "Channel %s filtered out: no email matching domains %s",
                channel_name,
                domain_whitelist,
            )
            return None

        email_str = primary_email or (emails[0] if emails else "")
        domain_str = primary_domain or ""

        phone_str = phones[0] if phones else ""

        if not (email_str or phone_str):
            # No contact info found; keep if whitelist is empty but skip otherwise
            if domain_whitelist:
                self.logger.debug(
                    "Channel %s has no contact info; skipping due to whitelist.",
                    channel_name,
                )
                return None

        return ChannelContact(
            Channel_url=channel_url,
            Channel_name=channel_name,
            Email=email_str,
            Domain_email=domain_str,
            Phone=phone_str,
            Description=description,
        )