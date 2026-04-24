import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine
from app.models import DailySummary, NewsItem
from app.core.config import get_settings
from app.services.sample_data import SAMPLE_NEWS_ITEMS, SAMPLE_SUMMARY_DATE, sample_category_counts, title_hash

logger = logging.getLogger(__name__)


def init_database() -> None:
    from sqlalchemy import text

    # For production, prefer: alembic upgrade head
    # create_all() is kept as a fallback for development and first-time setup.
    Base.metadata.create_all(bind=engine)
    # Lightweight additive migration for new backfill-status columns (idempotent).
    migrations = (
        "ALTER TABLE tracked_products ADD COLUMN IF NOT EXISTS backfill_status VARCHAR(20) NOT NULL DEFAULT 'idle'",
        "ALTER TABLE tracked_products ADD COLUMN IF NOT EXISTS backfill_started_at TIMESTAMPTZ",
        "ALTER TABLE tracked_products ADD COLUMN IF NOT EXISTS backfill_error TEXT",
        "ALTER TABLE tracked_products ADD COLUMN IF NOT EXISTS backfill_last_result JSONB",
        # visible_in_feed: snapshot of feed visibility at ingest time so that
        # post-ingest re-enrichment (e.g. summary model switch) cannot hide
        # previously-surfaced items. Backfill existing rows to True.
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS visible_in_feed BOOLEAN NOT NULL DEFAULT TRUE",
        # Corporate dynamics tagging (see app.services.corporate_dynamics).
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS company_name VARCHAR(255)",
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS corporate_signals JSONB",
        # Backfill: compute one-time per row so that only items currently
        # passing the (new) relevance gate start as visible. After this,
        # re-enrichment cannot flip visible_in_feed False -> True or
        # True -> False silently (see upsert_news_items).
        (
            "UPDATE news_items SET visible_in_feed = "
            "(relevance_to_cell_therapy IS NOT NULL "
            f"AND relevance_to_cell_therapy >= 0.7 "
            "AND category != 'Other')"
        ),
    )
    with engine.begin() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.warning("tracked_products migration step failed: %s (%s)", stmt, exc)
    if get_settings().seed_sample_data:
        with Session(engine) as db:
            seed_database(db)


def seed_database(db: Session) -> None:
    existing_count = db.scalar(select(NewsItem.id).limit(1))
    if existing_count is not None:
        return

    logger.info("Seeding deterministic development data.")
    news_items = []
    for item in SAMPLE_NEWS_ITEMS:
        news_items.append(NewsItem(**item, title_hash=title_hash(item["title"])))

    db.add_all(news_items)
    db.flush()

    top_events = [
        {
            "title": item.title,
            "category": item.category,
            "canonical_url": item.canonical_url,
            "source_name": item.source_name,
            "published_at": item.published_at.isoformat(),
            "short_summary": item.short_summary,
        }
        for item in news_items[:4]
    ]
    db.add(
        DailySummary(
            summary_date=SAMPLE_SUMMARY_DATE,
            daily_summary=(
                "Biomedicine and cell therapy updates today are led by financing, "
                "clinical-regulatory progress, and execution-focused manufacturing "
                "partnerships. This optional sample summary is stored in PostgreSQL."
            ),
            top_events=top_events,
            trend_signal=(
                "Financing and platform execution updates are more visible than broad "
                "policy activity in this seeded snapshot."
            ),
            category_counts=sample_category_counts(),
            model_name="glm5-stub",
            generated_at=datetime(2026, 4, 12, 7, 40, tzinfo=UTC),
        )
    )
    db.commit()
