import re
from typing import Iterable, List, Optional, Tuple

EMAIL_REGEX = re.compile(
    r"""
    [a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+   # local part
    @
    [a-zA-Z0-9-]+                      # domain name
    (?:\.[a-zA-Z0-9-]+)*               # optional subdomains
    """,
    re.VERBOSE,
)

PHONE_REGEX = re.compile(
    r"""
    (?:
        \+?\d{1,3}[\s-]??               # country code
    )?
    (?:\(?\d{2,4}\)?[\s-]??)?           # area code
    \d{3,4}[\s-]??\d{3,4}               # local number
    """,
    re.VERBOSE,
)

def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    emails = EMAIL_REGEX.findall(text)
    # Normalize and deduplicate while preserving order
    seen = set()
    result = []
    for email in emails:
        e = email.strip()
        if not e:
            continue
        if e not in seen:
            seen.add(e)
            result.append(e)
    return result

def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    phones = PHONE_REGEX.findall(text)
    cleaned: List[str] = []
    seen = set()
    for phone in phones:
        p = re.sub(r"\s+", " ", phone).strip()
        if len(re.sub(r"\D", "", p)) < 7:
            # Reject obviously too-short numbers
            continue
        if p not in seen:
            seen.add(p)
            cleaned.append(p)
    return cleaned

def choose_best_email_for_domains(
    emails: Iterable[str],
    domain_whitelist: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Pick the email that best matches a domain whitelist.
    Returns (email, '@domain') or (None, None) if nothing matches.

    If whitelist is empty or None, attempts to return the first found email
    and its domain.
    """
    emails = list(emails)
    if not emails:
        return None, None

    if not domain_whitelist:
        email = emails[0]
        domain = extract_domain(email)
        return email, domain

    normalized_whitelist = [d.lower() for d in domain_whitelist]

    for email in emails:
        domain = extract_domain(email)
        if not domain:
            continue
        if any(domain == d or domain.endswith(d) for d in normalized_whitelist):
            return email, domain

    return None, None

def extract_domain(email: str) -> Optional[str]:
    if "@" not in email:
        return None
    _, domain = email.split("@", 1)
    domain = domain.strip().lower()
    if not domain:
        return None
    return "@" + domain