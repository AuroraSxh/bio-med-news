from datetime import UTC, datetime

from app.models import NewsItem, TrackedProduct
from app.services.product_tracking import (
    _build_google_news_queries,
    _draft_date_to_datetime,
    _fallback_timeline_events,
    _phase_label,
    slugify_product_name,
)


def test_slugify_product_name_normalizes_spaces_and_symbols():
    assert slugify_product_name("CB-010 / Allo CAR-T") == "cb-010-allo-car-t"


def test_phase_label_detects_highest_phase():
    assert _phase_label("updated phase iii study in oncology") == "Phase 3"
    assert _phase_label("company announced preclinical research progress") == "Preclinical"


def test_build_google_news_queries_include_anchor_and_stages():
    product = TrackedProduct(display_name="CB-010", company_name="Caribou Biosciences")
    queries = _build_google_news_queries(product)
    assert queries[0] == '"CB-010" "Caribou Biosciences"'
    assert any("phase 1" in query.lower() for query in queries)


def test_fallback_timeline_events_detects_phase_start():
    product = TrackedProduct(display_name="CB-010", indications=["NHL"])
    item = NewsItem(
        id=1,
        title="Caribou starts Phase 1 trial for CB-010",
        canonical_url="https://example.com/cb-010",
        source_name="Example",
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
        category="Clinical/Regulatory Progress",
        short_summary="The company initiated a Phase 1 trial.",
        content_text="Caribou announced initiation of a Phase 1 clinical trial for CB-010 in NHL.",
        title_hash="hash",
    )
    events = _fallback_timeline_events(product, item)
    assert len(events) == 1
    assert events[0].milestone_type == "phase_start"
    assert events[0].phase_label == "Phase 1"


def test_draft_date_to_datetime_handles_year_month_day_precisions():
    assert _draft_date_to_datetime("2026", "year") == datetime(2026, 1, 1, tzinfo=UTC)
    assert _draft_date_to_datetime("2026-04", "month") == datetime(2026, 4, 1, tzinfo=UTC)
    assert _draft_date_to_datetime("2026-04-17", "day") == datetime(2026, 4, 17, tzinfo=UTC)
