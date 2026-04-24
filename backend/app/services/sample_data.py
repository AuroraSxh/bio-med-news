from datetime import UTC, date, datetime
from hashlib import sha256

from app.core.categories import CATEGORIES

SAMPLE_SUMMARY_DATE = date(2026, 4, 12)


def title_hash(title: str) -> str:
    normalized = " ".join(title.casefold().split())
    return sha256(normalized.encode("utf-8")).hexdigest()


SAMPLE_NEWS_ITEMS = [
    {
        "title": "Cell therapy developer closes Series B round for manufacturing scale-up",
        "canonical_url": "https://example.org/news/cell-therapy-series-b",
        "source_name": "Example Biotech Wire",
        "published_at": datetime(2026, 4, 12, 7, 30, tzinfo=UTC),
        "category": "Financing",
        "short_summary": "The company said proceeds will support process development, clinical operations, and expanded vector manufacturing capacity.",
        "content_text": "Deterministic seed item for financing and manufacturing readiness.",
        "image_url": None,
        "language": "en",
        "entities": ["Example Cell Therapeutics"],
        "importance_score": 0.82,
        "relevance_to_cell_therapy": 0.94,
    },
    {
        "title": "Regulator clears early-stage trial amendment for allogeneic CAR-T program",
        "canonical_url": "https://example.org/news/allogeneic-car-t-amendment",
        "source_name": "Clinical Update Daily",
        "published_at": datetime(2026, 4, 12, 6, 50, tzinfo=UTC),
        "category": "Clinical/Regulatory Progress",
        "short_summary": "The update allows the sponsor to enroll an additional dose cohort while maintaining existing safety monitoring requirements.",
        "content_text": "Deterministic seed item for clinical and regulatory progress.",
        "image_url": None,
        "language": "en",
        "entities": ["AlloCell Bio"],
        "importance_score": 0.78,
        "relevance_to_cell_therapy": 0.91,
    },
    {
        "title": "Academic group reports preclinical data for macrophage engineering platform",
        "canonical_url": "https://example.org/news/macrophage-engineering-preclinical",
        "source_name": "Translational Research News",
        "published_at": datetime(2026, 4, 12, 5, 20, tzinfo=UTC),
        "category": "R&D",
        "short_summary": "The study describes an engineered macrophage approach with improved tumor trafficking in mouse models.",
        "content_text": "Deterministic seed item for translational R&D.",
        "image_url": None,
        "language": "en",
        "entities": ["University Translational Center"],
        "importance_score": 0.66,
        "relevance_to_cell_therapy": 0.86,
    },
    {
        "title": "Biotech and CDMO announce cell therapy manufacturing collaboration",
        "canonical_url": "https://example.org/news/cdmo-cell-therapy-collaboration",
        "source_name": "BioProcess Monitor",
        "published_at": datetime(2026, 4, 11, 22, 15, tzinfo=UTC),
        "category": "Partnership/Licensing",
        "short_summary": "The agreement covers technology transfer, clinical batch production, and quality-system alignment for an autologous program.",
        "content_text": "Deterministic seed item for a manufacturing collaboration.",
        "image_url": None,
        "language": "en",
        "entities": ["Northbridge CDMO", "VectorCell"],
        "importance_score": 0.71,
        "relevance_to_cell_therapy": 0.9,
    },
    {
        "title": "Industry group publishes draft recommendations for advanced therapy logistics",
        "canonical_url": "https://example.org/news/advanced-therapy-logistics-guidance",
        "source_name": "Policy & Bioindustry Review",
        "published_at": datetime(2026, 4, 11, 18, 0, tzinfo=UTC),
        "category": "Policy/Industry Environment",
        "short_summary": "The recommendations focus on chain-of-identity controls, cryogenic transport handoffs, and deviation reporting.",
        "content_text": "Deterministic seed item for policy and industry environment coverage.",
        "image_url": None,
        "language": "en",
        "entities": ["Advanced Therapy Industry Forum"],
        "importance_score": 0.62,
        "relevance_to_cell_therapy": 0.79,
    },
    {
        "title": "Cell therapy unit appoints new head of technical operations",
        "canonical_url": "https://example.org/news/technical-operations-appointment",
        "source_name": "Biopharma People Moves",
        "published_at": datetime(2026, 4, 11, 16, 35, tzinfo=UTC),
        "category": "M&A/Organization",
        "short_summary": "The appointment is positioned around late-stage readiness and manufacturing network coordination.",
        "content_text": "Deterministic seed item for organization updates.",
        "image_url": None,
        "language": "en",
        "entities": ["CureCell Therapeutics"],
        "importance_score": 0.44,
        "relevance_to_cell_therapy": 0.72,
    },
]


def sample_category_counts() -> dict[str, int]:
    counts = {category: 0 for category in CATEGORIES}
    for item in SAMPLE_NEWS_ITEMS:
        counts[item["category"]] += 1
    return counts
