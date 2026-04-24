from datetime import UTC, date, datetime
from typing import Any

from app.core.categories import CATEGORIES
from app.models import NewsItem
from app.schemas.pipeline import DailySummaryDraft, DailySummaryEvent
from app.services.classification import category_counts
from app.services.glm5_client import GLM5Client


MAX_SUMMARY_INPUT_ITEMS = 20
MIN_TOP_EVENTS = 3


def generate_daily_summary(
    items: list[NewsItem],
    summary_date: date,
    glm5: GLM5Client | None = None,
    model_name: str | None = None,
) -> tuple[DailySummaryDraft | None, str | None]:
    if not items:
        return None, None

    # Bug fix: regenerate must be read-only over news_items — do NOT re-enrich here or category/relevance will be overwritten by the new model and the list_news gate will hide previously-stored items.
    ranked_items = _rank_summary_items(items)
    counts = category_counts(item.category for item in ranked_items)
    item_payload = [_item_payload(item) for item in ranked_items[:MAX_SUMMARY_INPUT_ITEMS]]
    client = glm5 or GLM5Client()
    model_summary = client.summarize_day(item_payload, counts, model_name=model_name)
    if model_summary is not None:
        return _normalize_summary(model_summary, ranked_items, counts), model_name or client.settings.glm5_model_name
    return _fallback_summary(ranked_items, summary_date, counts), "deterministic-fallback"


def _item_payload(item: NewsItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "category": item.category,
        "canonical_url": item.canonical_url,
        "source_name": item.source_name,
        "published_at": _iso(item.published_at),
        "short_summary": item.short_summary,
        "importance_score": item.importance_score,
        "relevance_to_cell_therapy": item.relevance_to_cell_therapy,
    }


def _normalize_summary(draft: DailySummaryDraft, ranked_items: list[NewsItem], counts: dict[str, int]) -> DailySummaryDraft:
    cleaned_events = list(draft.top_events[:5])
    if len(cleaned_events) < min(MIN_TOP_EVENTS, len(ranked_items)):
        existing_urls = {str(event.canonical_url) for event in cleaned_events}
        for item in ranked_items:
            if item.canonical_url in existing_urls:
                continue
            cleaned_events.append(_event_from_item(item))
            existing_urls.add(item.canonical_url)
            if len(cleaned_events) >= min(5, len(ranked_items)):
                break
    return DailySummaryDraft(
        daily_summary=draft.daily_summary,
        top_events=cleaned_events,
        trend_signal=draft.trend_signal,
        category_counts={category: int(draft.category_counts.get(category, counts.get(category, 0))) for category in CATEGORIES},
        category_summaries=draft.category_summaries,
    )


def _fallback_summary(items: list[NewsItem], summary_date: date, counts: dict[str, int]) -> DailySummaryDraft:
    top_items = items[:5]
    leading_categories = [category for category, count in counts.items() if count > 0][:3]
    top_event_titles = "；".join(item.title for item in top_items[:3])
    daily_summary = (
        f"{summary_date.isoformat()} 生物医药与细胞治疗资讯以 "
        f"{'、'.join(leading_categories) if leading_categories else '综合'} 方向为主。"
        f"重点条目包括：{top_event_titles}。"
    )
    # Fallback category summaries: group items by category and summarize
    cat_summaries: dict[str, str] = {}
    for cat, count in counts.items():
        if count > 0:
            cat_items = [item for item in items if item.category == cat]
            if cat_items:
                titles = "；".join(item.title for item in cat_items[:3])
                cat_summaries[cat] = f"共 {count} 条：{titles}。"

    return DailySummaryDraft(
        daily_summary=daily_summary,
        top_events=[_event_from_item(item) for item in top_items],
        trend_signal=_trend_signal(counts),
        category_counts=counts,
        category_summaries=cat_summaries,
    )


def _trend_signal(counts: dict[str, int]) -> str:
    non_zero = [(category, count) for category, count in counts.items() if count > 0]
    if not non_zero:
        return "暂无明显的分类集中趋势。"
    ordered = sorted(non_zero, key=lambda item: item[1], reverse=True)
    return f"本次采集中热度最高的分类为 {'、'.join(category for category, _ in ordered[:3])}。"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.isoformat()


def _rank_summary_items(items: list[NewsItem]) -> list[NewsItem]:
    ranked = sorted(
        items,
        key=lambda item: (
            item.relevance_to_cell_therapy or 0,
            item.importance_score or 0,
            item.published_at or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )
    selected: list[NewsItem] = []
    category_seen: set[str] = set()
    for item in ranked:
        if item.category in category_seen and len(category_seen) < min(len(CATEGORIES), len(ranked), 4):
            continue
        selected.append(item)
        category_seen.add(item.category)
        if len(selected) >= MAX_SUMMARY_INPUT_ITEMS:
            break

    selected_ids = {item.id for item in selected}
    for item in ranked:
        if item.id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.id)
        if len(selected) >= MAX_SUMMARY_INPUT_ITEMS:
            break
    return selected


def _event_from_item(item: NewsItem) -> DailySummaryEvent:
    return DailySummaryEvent(
        title=item.title,
        category=item.category,
        canonical_url=item.canonical_url,
        source_name=item.source_name,
        published_at=item.published_at,
        short_summary=item.short_summary,
    )
