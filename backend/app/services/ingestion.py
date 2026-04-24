import logging
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.schemas.pipeline import CandidateNewsItem, IngestionRunResult
from app.services.enrichment import enrich_items, normalize_title, title_hash
from app.services.news_repository import list_news_for_summary, upsert_daily_summary, upsert_news_items
from app.services.sources import fetch_all_sources
from app.services.summary import generate_daily_summary

logger = logging.getLogger(__name__)


def run_ingestion_cycle(db: Session, trigger: str = "scheduled", summary_date: date | None = None) -> IngestionRunResult:
    run_date = summary_date or datetime.now(UTC).date()
    logger.info("ingestion run start trigger=%s summary_date=%s", trigger, run_date.isoformat())

    candidates, failed_sources = fetch_all_sources()
    logger.info("ingestion normalization count=%s failed_sources=%s", len(candidates), len(failed_sources))

    # Filter out articles older than 7 days
    cutoff = datetime.now(UTC) - timedelta(days=7)
    fresh_candidates = [c for c in candidates if c.published_at >= cutoff]
    stale_count = len(candidates) - len(fresh_candidates)
    if stale_count:
        logger.info("ingestion freshness filter removed=%s older_than=%s", stale_count, cutoff.date().isoformat())
    candidates = fresh_candidates

    deduped, duplicate_in_batch = dedupe_candidates(candidates)
    logger.info("ingestion batch dedupe kept=%s duplicates=%s", len(deduped), duplicate_in_batch)

    enriched = enrich_items(deduped)
    logger.info("ingestion classified/enriched count=%s", len(enriched))

    inserted_count, updated_count, duplicate_count = upsert_news_items(db, enriched)
    logger.info(
        "ingestion persistence inserted=%s updated=%s duplicates_existing=%s",
        inserted_count,
        updated_count,
        duplicate_count,
    )

    summary_items = list_news_for_summary(db, run_date)
    if summary_items and not any(item.published_at.date() == run_date for item in summary_items):
        logger.info(
            "daily summary using latest stored items because no same-day items were available date=%s items=%s",
            run_date.isoformat(),
            len(summary_items),
        )
    summary, model_name = generate_daily_summary(summary_items, run_date)
    summary_available = summary is not None
    if summary is not None:
        upsert_daily_summary(db, run_date, summary, model_name=model_name)
        logger.info("daily summary persisted date=%s model=%s items=%s", run_date.isoformat(), model_name, len(summary_items))
    else:
        logger.info("daily summary skipped date=%s reason=no_same_day_items", run_date.isoformat())

    result = IngestionRunResult(
        trigger=trigger,
        fetched_count=len(candidates),
        normalized_count=len(deduped),
        inserted_count=inserted_count,
        updated_count=updated_count,
        duplicate_count=duplicate_in_batch + duplicate_count,
        failed_sources=failed_sources,
        summary_available=summary_available,
    )
    logger.info("ingestion run completion %s", result.model_dump())
    return result


def dedupe_candidates(items: list[CandidateNewsItem]) -> tuple[list[CandidateNewsItem], int]:
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    seen_titles: list[str] = []
    deduped: list[CandidateNewsItem] = []
    duplicates = 0
    for item in items:
        url = str(item.canonical_url)
        digest = title_hash(item.title)
        normalized_title = normalize_title(item.title)
        if url in seen_urls or digest in seen_hashes or _is_near_duplicate_title(normalized_title, seen_titles):
            duplicates += 1
            continue
        seen_urls.add(url)
        seen_hashes.add(digest)
        seen_titles.append(normalized_title)
        deduped.append(item)
    return deduped, duplicates


def _is_near_duplicate_title(title: str, seen_titles: list[str]) -> bool:
    if len(title) < 32:
        return False
    return any(SequenceMatcher(None, title, seen_title).ratio() >= 0.94 for seen_title in seen_titles)
