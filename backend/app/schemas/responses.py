from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    time: datetime
    database: str


class CategoriesResponse(BaseModel):
    categories: list[str]


class NewsItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    canonical_url: HttpUrl
    source_name: str
    published_at: datetime
    category: str
    short_summary: str
    image_url: HttpUrl | None = None
    language: str | None = "en"
    entities: list[str] | None = None
    importance_score: float | None = Field(default=None, ge=0, le=1)
    relevance_to_cell_therapy: float | None = Field(default=None, ge=0, le=1)


class Pagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class NewsFilters(BaseModel):
    category: str | None
    date: date | None
    q: str | None
    sort: str


class NewsListResponse(BaseModel):
    items: list[NewsItemResponse]
    pagination: Pagination
    filters: NewsFilters
    last_updated_at: datetime
    category_counts: dict[str, int] = {}


class TopEvent(BaseModel):
    title: str
    category: str
    canonical_url: HttpUrl
    source_name: str | None = None
    published_at: datetime | None = None
    short_summary: str | None = None


class TodaySummaryResponse(BaseModel):
    available: bool
    summary_date: date
    daily_summary: str | None
    top_events: list[TopEvent]
    trend_signal: str | None
    category_counts: dict[str, int]
    category_summaries: dict[str, str] = {}
    model_name: str | None
    generated_at: datetime | None


class RefreshAcceptedResponse(BaseModel):
    accepted: bool
    message: str
    requested_at: datetime


class ModelInfo(BaseModel):
    id: str
    label: str
    type: str
    description: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    current: str


class CorporateDynamicsBuckets(BaseModel):
    layoffs: list[NewsItemResponse] = Field(default_factory=list)
    new_pipeline: list[NewsItemResponse] = Field(default_factory=list)
    financing: list[NewsItemResponse] = Field(default_factory=list)


class CorporateCompanyEntry(BaseModel):
    name: str
    chinese_name: str
    signals: CorporateDynamicsBuckets
    last_updated_at: datetime | None = None


class CorporateDynamicsResponse(BaseModel):
    companies: list[CorporateCompanyEntry]
    total_companies: int
