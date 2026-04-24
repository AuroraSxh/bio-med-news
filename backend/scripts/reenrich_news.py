"""One-time re-enrichment of legacy news_items rows.

Many rows were enriched under an older, more permissive prompt and carry
wrong `category` / `relevance_to_cell_therapy`. This script re-runs the
current `enrich_items` pipeline and writes the updated fields back.

Usage:
    python -m scripts.reenrich_news                 # rows older than cutoff (1 day)
    python -m scripts.reenrich_news --all           # every row
    python -m scripts.reenrich_news --limit 100     # cap total rows processed
    python -m scripts.reenrich_news --all --limit 500
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow `python scripts/reenrich_news.py` from the backend/ dir.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import NewsItem  # noqa: E402
from app.schemas.pipeline import CandidateNewsItem  # noqa: E402
from app.services.enrichment import enrich_items  # noqa: E402

BATCH_SIZE = 20
DEFAULT_CUTOFF_DAYS = 1

logger = logging.getLogger("reenrich_news")


def _to_candidate(row: NewsItem) -> CandidateNewsItem:
    return CandidateNewsItem(
        title=row.title,
        canonical_url=row.canonical_url,
        source_name=row.source_name,
        published_at=row.published_at,
        content_text=row.content_text,
        raw_summary=row.short_summary,
        image_url=row.image_url,
        language=row.language,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-enrich legacy news_items rows.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-enrich every row regardless of updated_at cutoff.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to process.",
    )
    parser.add_argument(
        "--cutoff-days",
        type=int,
        default=DEFAULT_CUTOFF_DAYS,
        help="When --all is not set, only rows with updated_at older than "
             "N days are processed (default: 1).",
    )
    return parser.parse_args()


def select_rows(session, *, reenrich_all: bool, limit: int | None, cutoff_days: int) -> list[NewsItem]:
    stmt = select(NewsItem).order_by(NewsItem.id.asc())
    if not reenrich_all:
        cutoff = datetime.now(UTC) - timedelta(days=cutoff_days)
        stmt = stmt.where(NewsItem.updated_at < cutoff)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args()

    session = SessionLocal()
    try:
        rows = select_rows(
            session,
            reenrich_all=args.all,
            limit=args.limit,
            cutoff_days=args.cutoff_days,
        )
        total = len(rows)
        print(f"[reenrich] selected {total} row(s) for re-enrichment "
              f"(all={args.all}, limit={args.limit}, cutoff_days={args.cutoff_days})")
        if total == 0:
            return 0

        updated = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch_rows = rows[batch_start : batch_start + BATCH_SIZE]
            candidates = [_to_candidate(r) for r in batch_rows]
            classified = enrich_items(candidates)
            by_url = {str(c.canonical_url): c for c in classified}

            for row in batch_rows:
                c = by_url.get(row.canonical_url)
                if c is None:
                    continue
                row.category = c.category
                row.short_summary = c.short_summary
                row.importance_score = c.importance_score
                row.relevance_to_cell_therapy = c.relevance_to_cell_therapy
                # No dedicated `enriched_at` column; bump updated_at to now so
                # subsequent runs with a cutoff skip this row.
                row.updated_at = datetime.now(UTC)
                updated += 1

            session.commit()
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"[reenrich] batch {batch_num}/{total_batches} "
                  f"processed={len(batch_rows)} updated_total={updated}")

        print(f"[reenrich] done. {updated}/{total} rows updated.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
