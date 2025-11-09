import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Ensure the src folder is on the path so we can import sibling packages as namespace packages
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from parsers.youtube_parser import YouTubeScraper, ChannelContact  # type: ignore
from outputs.export_manager import ExportManager  # type: ignore

def setup_logger(verbosity: int) -> logging.Logger:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("youtube-email-phone-scraper")
    return logger

def load_json_file(path: Path, logger: logging.Logger) -> dict:
    if not path.exists():
        logger.error("JSON file not found: %s", path)
        raise FileNotFoundError(f"JSON file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", path, exc)
        raise

def normalize_domains(raw) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    result = []
    for item in raw:
        if not item:
            continue
        item = item.strip()
        # Ensure domain starts with '@' for consistency
        if not item.startswith("@"):
            item = "@" + item
        result.append(item.lower())
    return result

def resolve_output_dir(default_dir: Optional[str]) -> Path:
    if default_dir:
        return (PROJECT_ROOT / default_dir).resolve()
    # Fallback to ./data
    return (PROJECT_ROOT / "data").resolve()

def run(config_path: Path, input_path: Path, verbosity: int) -> None:
    logger = setup_logger(verbosity)
    logger.debug("Project root resolved to %s", PROJECT_ROOT)

    config = load_json_file(config_path, logger)
    input_data = load_json_file(input_path, logger)

    api_key = config.get("youtube_api_key") or ""
    if not api_key:
        logger.error(
            "YouTube API key missing. Please set 'youtube_api_key' in %s.",
            config_path,
        )
        raise SystemExit(1)

    default_output_dir = config.get("default_output_dir")
    output_dir = resolve_output_dir(default_output_dir)

    keyword = input_data.get("keyword") or input_data.get("query") or ""
    if not keyword:
        logger.error("Input is missing required field 'keyword'.")
        raise SystemExit(1)

    max_results = int(input_data.get("max_results") or 50)
    raw_domains = input_data.get("domainemail") or input_data.get("domain_email")
    allowed_domains = normalize_domains(raw_domains)
    export_formats = input_data.get("export_formats") or ["json"]

    logger.info("Starting YouTube scraping for keyword '%s'", keyword)
    logger.info(
        "Max results: %s | Domain filters: %s | Export formats: %s",
        max_results,
        allowed_domains or "none",
        ", ".join(export_formats),
    )

    scraper = YouTubeScraper(api_key=api_key, logger=logger)
    contacts: List[ChannelContact] = scraper.scrape_contacts(
        keyword=keyword,
        max_results=max_results,
        domain_whitelist=allowed_domains,
    )

    logger.info("Scraping completed. Extracted %d contacts.", len(contacts))

    exporter = ExportManager(output_dir=output_dir, logger=logger)
    outputs = exporter.export(contacts, export_formats)

    for fmt, path in outputs.items():
        logger.info("Exported %s to %s", fmt.upper(), path)

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YouTube Email & Phone Scraper - CLI entrypoint"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(SRC_DIR / "config" / "settings.example.json"),
        help="Path to settings JSON file (default: src/config/settings.example.json)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(PROJECT_ROOT / "data" / "input.sample.json"),
        help="Path to input JSON file describing the scrape parameters "
        "(default: data/input.sample.json)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (use -v or -vv)",
    )
    return parser.parse_args(argv)

if __name__ == "__main__":
    args = parse_args()
    try:
        run(
            config_path=Path(args.config).resolve(),
            input_path=Path(args.input).resolve(),
            verbosity=args.verbose,
        )
    except KeyboardInterrupt:
        logging.getLogger("youtube-email-phone-scraper").warning("Interrupted by user.")
        raise SystemExit(130)