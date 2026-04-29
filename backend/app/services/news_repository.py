from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from typing import Literal

from sqlalchemy import Select, delete, func, or_, select, true
from sqlalchemy.orm import Session

from app.models import DailySummary, NewsItem
from app.schemas.pipeline import ClassifiedNewsItem, DailySummaryDraft
from app.schemas.responses import (
    NewsFilters,
    NewsListResponse,
    Pagination,
    TodaySummaryResponse,
)
from app.services.enrichment import CELL_THERAPY_RELEVANCE_THRESHOLD


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, tzinfo=UTC)
    end = datetime.combine(value, time.max, tzinfo=UTC)
    return start, end


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def list_news(
    db: Session,
    page: int,
    page_size: int,
    category: str | None,
    report_date: date | None,
    q: str | None,
    sort: Literal["published_at_desc", "published_at_asc"],
) -> NewsListResponse:
    # Shared filters (date + search) applied to both item query and category counts
    shared_filters: list[object] = []
    if report_date:
        shared_filters.append(func.date(NewsItem.published_at) == report_date)
    if q:
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        needle = f"%{escaped_q}%"
        shared_filters.append(or_(
            NewsItem.title.ilike(needle, escape="\\"),
            NewsItem.source_name.ilike(needle, escape="\\"),
            NewsItem.short_summary.ilike(needle, escape="\\"),
        ))

    # Default relevance gate: when no explicit category is requested, hide
    # low-relevance / "Other" items from the main feed. Explicit category
    # filters (including "Other") bypass the gate so callers can still drill in.
    #
    # SAFETY: items that were once surfaced to users (visible_in_feed=True)
    # stay visible even if a later re-enrichment demoted their category or
    # relevance score. This prevents items from silently disappearing after
    # a summary-model switch or worker-triggered re-classification.
    relevance_gate = [
        NewsItem.visible_in_feed.is_(True),
    ]

    # Category filter only applied to item query, not to category counts
    item_filters = list(shared_filters)
    if category:
        item_filters.append(NewsItem.category == category)
    else:
        item_filters.extend(relevance_gate)

    base_query: Select[tuple[NewsItem]] = select(NewsItem)
    count_query = select(func.count()).select_from(NewsItem)
    if item_filters:
        base_query = base_query.where(*item_filters)
        count_query = count_query.where(*item_filters)

    if sort == "published_at_asc":
        base_query = base_query.order_by(NewsItem.published_at.asc(), NewsItem.id.asc())
    else:
        base_query = base_query.order_by(NewsItem.published_at.desc(), NewsItem.id.desc())

    total_items = db.scalar(count_query) or 0
    items = db.scalars(base_query.offset((page - 1) * page_size).limit(page_size)).all()
    last_updated_at = db.scalar(select(func.max(NewsItem.updated_at))) or datetime.now(UTC)

    # Real category counts from database (shared filters only, no category filter).
    # Apply the same relevance gate so category tile totals match the main feed
    # (i.e. the "All" tab count excludes Other / low-relevance items).
    cat_count_query = select(NewsItem.category, func.count()).group_by(NewsItem.category)
    cat_count_filters = list(shared_filters) + relevance_gate
    cat_count_query = cat_count_query.where(*cat_count_filters)
    category_counts = dict(db.execute(cat_count_query).all())

    return NewsListResponse(
        items=items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=max(1, ceil(total_items / page_size)),
        ),
        filters=NewsFilters(category=category, date=report_date, q=q, sort=sort),
        last_updated_at=_as_utc(last_updated_at) or datetime.now(UTC),
        category_counts=category_counts,
    )


def upsert_news_items(db: Session, items: list[ClassifiedNewsItem]) -> tuple[int, int, int]:
    if not items:
        return 0, 0, 0

    inserted_count = 0
    updated_count = 0
    duplicate_count = 0
    canonical_urls = [str(item.canonical_url) for item in items]
    title_hashes = [item.title_hash for item in items]
    existing_rows = db.scalars(
        select(NewsItem).where(
            or_(
                NewsItem.canonical_url.in_(canonical_urls),
                NewsItem.title_hash.in_(title_hashes),
            )
        )
    ).all()
    existing_by_url = {row.canonical_url: row for row in existing_rows}
    existing_by_hash = {row.title_hash: row for row in existing_rows}

    for item in items:
        canonical_url = str(item.canonical_url)
        existing = existing_by_url.get(canonical_url) or existing_by_hash.get(item.title_hash)
        passes_gate = (
            item.relevance_to_cell_therapy is not None
            and item.relevance_to_cell_therapy >= CELL_THERAPY_RELEVANCE_THRESHOLD
            and item.category != "Other"
        )
        values = {
            "title": item.title,
            "canonical_url": canonical_url,
            "source_name": item.source_name,
            "published_at": _as_utc(item.published_at) or item.published_at,
            "category": item.category,
            "short_summary": item.short_summary,
            "content_text": item.content_text,
            "image_url": str(item.image_url) if item.image_url else None,
            "language": item.language,
            "title_hash": item.title_hash,
            "entities": item.entities,
            "importance_score": item.importance_score,
            "relevance_to_cell_therapy": item.relevance_to_cell_therapy,
        }
        if existing is None:
            record = NewsItem(**values, visible_in_feed=passes_gate)
            db.add(record)
            existing_by_url[record.canonical_url] = record
            existing_by_hash[record.title_hash] = record
            inserted_count += 1
        else:
            duplicate_count += 1
            changed = False
            for key, value in values.items():
                if not _values_equal(getattr(existing, key), value):
                    setattr(existing, key, value)
                    changed = True
            # Monotonic visibility: only promote False -> True. Never demote
            # a previously-surfaced item just because a re-enrichment run
            # (e.g. after a summary-model switch) lowered its relevance.
            if passes_gate and not existing.visible_in_feed:
                existing.visible_in_feed = True
                changed = True
            if changed:
                updated_count += 1

    db.commit()
    return inserted_count, updated_count, duplicate_count


def _values_equal(left: object, right: object) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        return (_as_utc(left) or left).isoformat() == (_as_utc(right) or right).isoformat()
    return left == right


def list_news_for_summary(db: Session, summary_date: date, limit: int = 30) -> list[NewsItem]:
    # RSS-supplied `published_at` lags wall-clock — early on summary_date there
    # are often zero same-day items even though many were ingested overnight.
    # Use a rolling window ending at end-of-summary-date so the summary captures
    # ~36 hours of fresh coverage; fall through to the global latest only if
    # even that window is too sparse.
    _, end = _day_bounds(summary_date)
    window_start = end - timedelta(hours=36)
    window_items = db.scalars(
        select(NewsItem)
        .where(NewsItem.published_at >= window_start, NewsItem.published_at <= end)
        .order_by(
            NewsItem.relevance_to_cell_therapy.desc().nullslast(),
            NewsItem.importance_score.desc().nullslast(),
            NewsItem.published_at.desc(),
            NewsItem.id.desc(),
        )
        .limit(limit)
    ).all()
    if len(window_items) >= 5:
        return window_items

    seen_ids = {item.id for item in window_items}
    latest_items = db.scalars(
        select(NewsItem)
        .where(NewsItem.id.not_in(seen_ids) if seen_ids else true())
        .order_by(
            NewsItem.relevance_to_cell_therapy.desc().nullslast(),
            NewsItem.importance_score.desc().nullslast(),
            NewsItem.published_at.desc(),
            NewsItem.id.desc(),
        )
        .limit(max(0, limit - len(window_items)))
    ).all()
    return [*window_items, *latest_items]


def upsert_daily_summary(
    db: Session,
    summary_date: date,
    draft: DailySummaryDraft,
    model_name: str | None,
    generated_at: datetime | None = None,
) -> None:
    db.execute(delete(DailySummary).where(DailySummary.summary_date == summary_date))
    db.add(
        DailySummary(
            summary_date=summary_date,
            daily_summary=draft.daily_summary,
            top_events=[event.model_dump(mode="json", exclude_none=True) for event in draft.top_events],
            trend_signal=draft.trend_signal,
            category_counts=draft.category_counts,
            category_summaries=draft.category_summaries or {},
            model_name=model_name,
            generated_at=generated_at or datetime.now(UTC),
        )
    )
    db.commit()


def get_today_summary(db: Session, report_date: date | None) -> TodaySummaryResponse:
    summary_date = report_date or datetime.now(UTC).date()
    summary = db.scalar(
        select(DailySummary)
        .where(DailySummary.summary_date == summary_date)
        .order_by(DailySummary.generated_at.desc(), DailySummary.id.desc())
        .limit(1)
    )
    if summary is None:
        return TodaySummaryResponse(
            available=False,
            summary_date=summary_date,
            daily_summary=None,
            top_events=[],
            trend_signal=None,
            category_counts={},
            category_summaries={},
            model_name=None,
            generated_at=None,
        )

    return TodaySummaryResponse(
        available=True,
        summary_date=summary.summary_date,
        daily_summary=summary.daily_summary,
        top_events=summary.top_events,
        trend_signal=summary.trend_signal,
        category_counts=summary.category_counts,
        category_summaries=summary.category_summaries or {},
        model_name=summary.model_name,
        generated_at=_as_utc(summary.generated_at),
    )
