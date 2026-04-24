from datetime import UTC, datetime

from app.schemas.pipeline import CandidateNewsItem
from app.services.ingestion import dedupe_candidates


def _make_item(title: str, url: str = "https://example.com/default") -> CandidateNewsItem:
    return CandidateNewsItem(
        title=title,
        canonical_url=url,
        source_name="Test Source",
        published_at=datetime(2026, 4, 12, tzinfo=UTC),
        content_text=title,
        raw_summary=title,
        image_url=None,
        language="en",
    )


class TestDeduplication:
    def test_exact_url_dedup(self):
        items = [
            _make_item("Article One", "https://example.com/a"),
            _make_item("Article Two", "https://example.com/a"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 1
        assert dups == 1
        assert deduped[0].title == "Article One"

    def test_different_urls_kept(self):
        items = [
            _make_item("Article One", "https://example.com/a"),
            _make_item("Article Two", "https://example.com/b"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 2
        assert dups == 0

    def test_title_hash_dedup(self):
        items = [
            _make_item("Exact Same Title Here", "https://example.com/a"),
            _make_item("Exact Same Title Here", "https://example.com/b"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 1
        assert dups == 1

    def test_near_duplicate_title_detected(self):
        base_title = "FDA Approves New Cell Therapy Treatment for Lymphoma Patients in Clinical Trial"
        similar_title = "FDA Approves New Cell Therapy Treatment for Lymphoma Patients in Clinical Trials"
        items = [
            _make_item(base_title, "https://example.com/a"),
            _make_item(similar_title, "https://example.com/b"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 1
        assert dups == 1

    def test_short_titles_bypass_near_dup_check(self):
        items = [
            _make_item("Short Title", "https://example.com/a"),
            _make_item("Short Titl", "https://example.com/b"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 2
        assert dups == 0

    def test_dissimilar_titles_kept(self):
        items = [
            _make_item("Completely different article about gene therapy advances", "https://example.com/a"),
            _make_item("New funding round for biotech startup in San Francisco", "https://example.com/b"),
        ]
        deduped, dups = dedupe_candidates(items)
        assert len(deduped) == 2
        assert dups == 0

    def test_empty_input(self):
        deduped, dups = dedupe_candidates([])
        assert len(deduped) == 0
        assert dups == 0
