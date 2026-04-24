import logging
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from time import sleep
from time import struct_time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import urllib.request

from email.utils import parsedate_to_datetime

import feedparser
import httpx

from app.core.config import get_settings
from app.schemas.pipeline import CandidateNewsItem, SourceConfig

logger = logging.getLogger(__name__)

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAM_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid"}
USER_AGENT = "biomed-news-app/0.4 (+https://118.178.195.6)"
TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in TRACKING_PARAM_NAMES and not key.startswith(TRACKING_PARAM_PREFIXES)
    )
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            urlencode(query, doseq=True),
            "",
        )
    )


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(unescape(without_tags).split())
    return normalized or None


def parsed_time_to_datetime(value: struct_time | None, raw_date: str | None = None) -> datetime:
    if value is not None:
        return datetime(*value[:6], tzinfo=UTC)
    if raw_date:
        parsed = _parse_raw_date(raw_date)
        if parsed is not None:
            return parsed
    return datetime.now(UTC)


_RAW_DATE_FORMATS = (
    "%b %d, %Y %I:%M%p",   # "Apr 10, 2026 2:25AM"
    "%b %d, %Y %I:%M %p",  # "Apr 10, 2026 2:25 AM"
    "%Y-%m-%dT%H:%M:%S%z", # ISO 8601
    "%Y-%m-%d %H:%M:%S",   # "2026-04-10 02:25:00"
)


def _parse_raw_date(value: str) -> datetime | None:
    stripped = value.strip()
    # Normalize am/pm to uppercase for strptime %p
    normalized = re.sub(r"(?i)(am|pm)\s*$", lambda m: m.group().upper(), stripped)
    for fmt in _RAW_DATE_FORMATS:
        try:
            dt = datetime.strptime(normalized, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    # Try RFC 2822 (standard RSS date format)
    try:
        return parsedate_to_datetime(stripped)
    except (ValueError, TypeError):
        pass
    logger.warning("unparseable date string: %r", value)
    return None


def fetch_source(source: SourceConfig) -> list[CandidateNewsItem]:
    settings = get_settings()
    logger.info("source fetch start: %s %s", source.name, source.feed_url)
    content = _fetch_bytes(str(source.feed_url), source_name=source.name)
    parsed = feedparser.parse(content)
    if parsed.bozo:
        logger.warning("source parse warning for %s: %s", source.name, parsed.bozo_exception)

    items: list[CandidateNewsItem] = []
    max_items = min(source.max_items, settings.ingestion_max_items_per_source)
    skipped_count = 0
    for entry in parsed.entries[:max_items]:
        try:
            title = clean_text(getattr(entry, "title", None))
            link = getattr(entry, "link", None)
            if not title or not link or not _is_http_url(link):
                logger.info("source parse skipped item without title/link: %s", source.name)
                skipped_count += 1
                continue

            content_text = _entry_content_text(getattr(entry, "content", None))
            raw_summary = clean_text(getattr(entry, "summary", None))
            content_text = content_text or raw_summary or title

            image_url = None
            media_content = getattr(entry, "media_content", None)
            if media_content:
                image_url = media_content[0].get("url")

            raw_date = getattr(entry, "published", None) or getattr(entry, "updated", None)
            items.append(
                CandidateNewsItem(
                    title=title,
                    canonical_url=canonicalize_url(link),
                    source_name=source.name,
                    published_at=parsed_time_to_datetime(
                        getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None),
                        raw_date=raw_date,
                    ),
                    content_text=content_text,
                    raw_summary=raw_summary,
                    image_url=image_url,
                    language=getattr(entry, "language", None) or getattr(parsed.feed, "language", None) or "en",
                )
            )
        except Exception:
            logger.exception("source parse failure: %s", source.name)

    logger.info("source fetch end: %s normalized=%s skipped=%s", source.name, len(items), skipped_count)
    return items


def _fetch_bytes(url: str, source_name: str) -> bytes:
    settings = get_settings()
    with httpx.Client(timeout=settings.source_request_timeout_seconds, follow_redirects=True) as client:
        max_attempts = max(1, settings.source_request_max_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.get(url, headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
                return response.content
            except httpx.HTTPError as exc:
                status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                retryable = _is_retryable_http_error(exc, status_code)
                logger.warning(
                    "source fetch failure",
                    extra={
                        "retryable": retryable,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "source_name": source_name,
                        "url": url,
                        "status_code": status_code,
                        "error": str(exc),
                    },
                )
                if not retryable or attempt >= max_attempts:
                    break
                sleep(settings.source_request_backoff_seconds * (2 ** (attempt - 1)))

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=settings.source_request_timeout_seconds) as response:
        return response.read()


def fetch_all_sources(sources: list[SourceConfig] | None = None) -> tuple[list[CandidateNewsItem], list[str]]:
    all_items: list[CandidateNewsItem] = []
    failed_sources: list[str] = []
    for source in sources or load_sources():
        try:
            all_items.extend(fetch_source(source))
        except Exception:
            failed_sources.append(source.name)
            logger.exception("source fetch failure: %s", source.name)
    return all_items, failed_sources


def load_sources() -> list[SourceConfig]:
    settings = get_settings()
    if settings.ingestion_sources_json.strip():
        payload = json.loads(settings.ingestion_sources_json)
        source_label = "env:INGESTION_SOURCES_JSON"
    else:
        config_path = Path(settings.source_config_path)
        if not config_path.is_absolute():
            config_path = BACKEND_ROOT / config_path
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        source_label = str(config_path)

    if not isinstance(payload, list) or not payload:
        raise ValueError(f"source config must be a non-empty JSON array: {source_label}")

    sources = [SourceConfig.model_validate(item) for item in payload]
    logger.info("loaded source configuration", extra={"source_config": source_label, "source_count": len(sources)})
    return sources


def _entry_content_text(content: Iterable[object] | None) -> str | None:
    if not content:
        return None
    for part in content:
        value = part.get("value") if isinstance(part, dict) else getattr(part, "value", None)
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return None


def _is_http_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_retryable_http_error(exc: httpx.HTTPError, status_code: int | None) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)):
        return True
    return status_code in TRANSIENT_HTTP_STATUS_CODES
