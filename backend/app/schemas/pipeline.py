from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.core.categories import CATEGORIES


class SourceConfig(BaseModel):
    name: str
    feed_url: HttpUrl
    max_items: int = Field(default=12, ge=1, le=50)


class CandidateNewsItem(BaseModel):
    title: str
    canonical_url: HttpUrl
    source_name: str
    published_at: datetime
    content_text: str | None = None
    raw_summary: str | None = None
    image_url: HttpUrl | None = None
    language: str | None = "en"


class ClassifiedNewsItem(CandidateNewsItem):
    title_hash: str
    category: str
    short_summary: str
    entities: list[str] | None = None
    importance_score: float | None = Field(default=None, ge=0, le=1)
    relevance_to_cell_therapy: float | None = Field(default=None, ge=0, le=1)
    # Corporate-dynamics tagging (populated by enrichment; optional).
    company_name: str | None = None
    corporate_signals: list[str] | None = None

    @field_validator("category")
    @classmethod
    def category_is_allowed(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("category is not in the fixed taxonomy")
        return value


class ItemEnrichment(BaseModel):
    one_line_summary: str = Field(min_length=1, max_length=500)
    category: str
    entities: list[str] = Field(default_factory=list, max_length=12)
    importance_score: float = Field(ge=0, le=1)
    relevance_to_cell_therapy: float = Field(ge=0, le=1)

    @field_validator("category")
    @classmethod
    def category_is_allowed(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("category is not in the fixed taxonomy")
        return value


class DailySummaryEvent(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    category: str
    canonical_url: HttpUrl
    source_name: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    short_summary: str | None = Field(default=None, max_length=500)

    @field_validator("category")
    @classmethod
    def category_is_allowed(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("category is not in the fixed taxonomy")
        return value


class DailySummaryDraft(BaseModel):
    daily_summary: str = Field(min_length=1, max_length=2000)
    top_events: list[DailySummaryEvent] = Field(default_factory=list, min_length=0, max_length=5)
    trend_signal: str | None = Field(default=None, max_length=700)
    category_counts: dict[str, int]
    category_summaries: dict[str, str] = Field(default_factory=dict)

    @field_validator("category_counts")
    @classmethod
    def category_counts_use_allowed_categories(cls, value: dict[str, int]) -> dict[str, int]:
        unexpected = set(value) - set(CATEGORIES)
        if unexpected:
            raise ValueError(f"unexpected categories: {sorted(unexpected)}")
        return value


class IngestionRunResult(BaseModel):
    trigger: str
    fetched_count: int = 0
    normalized_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    failed_sources: list[str] = Field(default_factory=list)
    summary_available: bool = False
