from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


TRACKED_PRODUCT_STATUSES = {"draft", "active", "paused"}
PRODUCT_MILESTONE_TYPES = {
    "research",
    "preclinical",
    "ind_cta_iit",
    "phase_start",
    "phase_result",
    "regulatory",
    "partnering",
    "financing",
    "setback",
    "commercial",
    "other",
}
PRODUCT_DATE_PRECISIONS = {"year", "month", "day"}


class TrackedProductCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    indications: list[str] = Field(default_factory=list, max_length=12)
    modality: str | None = Field(default=None, max_length=80)


class ProductNewsMatch(BaseModel):
    is_relevant: bool
    matched_alias: str | None = Field(default=None, max_length=200)
    matched_company: str | None = Field(default=None, max_length=200)
    confidence: float = Field(ge=0, le=1)
    reason_short: str = Field(min_length=1, max_length=300)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: object) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            s = value.strip().casefold().rstrip("%")
            mapping = {"high": 0.9, "medium": 0.6, "mid": 0.6, "low": 0.3, "unknown": 0.3}
            if s in mapping:
                return mapping[s]
            try:
                num = float(s)
                if num > 1.0:
                    num /= 100.0
                return max(0.0, min(1.0, num))
            except ValueError:
                return 0.5
        return 0.5


class ProductTimelineEventDraft(BaseModel):
    event_date: str = Field(min_length=4, max_length=10)
    event_date_precision: str

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: object) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            s = value.strip().casefold().rstrip("%")
            mapping = {
                "high": 0.9,
                "medium": 0.6,
                "med": 0.6,
                "mid": 0.6,
                "moderate": 0.6,
                "low": 0.3,
                "very high": 0.95,
                "very low": 0.1,
                "unknown": 0.3,
            }
            if s in mapping:
                return mapping[s]
            try:
                num = float(s)
                if num > 1.0:
                    num = num / 100.0
                return max(0.0, min(1.0, num))
            except ValueError:
                return 0.5
        return 0.5

    @field_validator("event_date", mode="before")
    @classmethod
    def normalize_event_date(cls, value: object) -> str:
        import re as _re
        from datetime import UTC as _UTC, datetime as _dt
        if not isinstance(value, str):
            return _dt.now(_UTC).strftime("%Y-%m-%d")
        s = value.strip()
        if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return s
        if _re.fullmatch(r"\d{4}-\d{2}", s):
            return s
        if _re.fullmatch(r"\d{4}", s):
            return s
        m = _re.match(r"(\d{4})[/.](\d{1,2})(?:[/.](\d{1,2}))?", s)
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3)
            return f"{y}-{mo}-{d.zfill(2)}" if d else f"{y}-{mo}"
        m = _re.search(r"(19|20)\d{2}", s)
        if m:
            return m.group(0)
        return _dt.now(_UTC).strftime("%Y-%m-%d")
    milestone_type: str
    milestone_label: str = Field(min_length=1, max_length=160)
    phase_label: str | None = Field(default=None, max_length=80)
    headline: str = Field(min_length=1, max_length=500)
    event_summary: str = Field(min_length=1, max_length=800)
    indication: str | None = Field(default=None, max_length=200)
    region: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0, le=1)
    evidence_quote_short: str | None = Field(default=None, max_length=220)

    @field_validator("event_date_precision", mode="before")
    @classmethod
    def precision_is_allowed(cls, value: str) -> str:
        if not isinstance(value, str):
            return "day"
        v = value.strip().casefold()
        if v in PRODUCT_DATE_PRECISIONS:
            return v
        if v.startswith("y"):
            return "year"
        if v.startswith("m"):
            return "month"
        return "day"

    @field_validator("milestone_type", mode="before")
    @classmethod
    def milestone_type_is_allowed(cls, value: str) -> str:
        if not isinstance(value, str):
            return "other"
        v = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if v in PRODUCT_MILESTONE_TYPES:
            return v
        aliases = {
            "ind": "ind_cta_iit",
            "cta": "ind_cta_iit",
            "iit": "ind_cta_iit",
            "ind/cta/iit": "ind_cta_iit",
            "phase1_start": "phase_start",
            "phase_1_start": "phase_start",
            "clinical_start": "phase_start",
            "clinical_result": "phase_result",
            "trial_result": "phase_result",
            "trial_start": "phase_start",
            "approval": "regulatory",
            "fda_approval": "regulatory",
            "launch": "commercial",
            "deal": "partnering",
            "collaboration": "partnering",
            "licensing": "partnering",
            "funding": "financing",
            "round": "financing",
            "termination": "setback",
            "hold": "setback",
        }
        return aliases.get(v, "other")


class ProductTimelineExtraction(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    events: list[ProductTimelineEventDraft] = Field(default_factory=list, max_length=12)


class ProductAliasSuggestion(BaseModel):
    aliases: list[str] = Field(default_factory=list, max_length=8)
    confidence: float | None = None
    notes: str | None = Field(default=None, max_length=600)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            s = value.strip().casefold().rstrip("%")
            if not s:
                return None
            mapping = {
                "high": 0.9,
                "medium": 0.6,
                "med": 0.6,
                "mid": 0.6,
                "moderate": 0.6,
                "low": 0.3,
                "very high": 0.95,
                "very low": 0.1,
                "unknown": 0.3,
            }
            if s in mapping:
                return mapping[s]
            try:
                num = float(s)
                if num > 1.0:
                    num /= 100.0
                return max(0.0, min(1.0, num))
            except ValueError:
                return None
        return None

    @field_validator("aliases", mode="before")
    @classmethod
    def coerce_aliases(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            out: list[str] = []
            for v in value:
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        out.append(s)
            return out[:8]
        return []


class ProductNewsItemResponse(BaseModel):
    id: int
    title: str
    canonical_url: HttpUrl
    source_name: str
    published_at: datetime
    category: str
    short_summary: str
    match_source: str
    match_confidence: float | None = None


class ProductTimelineEventResponse(BaseModel):
    id: int
    event_date: datetime
    event_date_precision: str
    milestone_type: str
    milestone_label: str
    phase_label: str | None = None
    headline: str
    event_summary: str
    indication: str | None = None
    region: str | None = None
    confidence: float | None = None
    evidence_news_item_ids: list[int] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class TrackedProductListItemResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    company_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    indications: list[str] = Field(default_factory=list)
    modality: str | None = None
    status: str
    timeline_event_count: int = 0
    linked_news_count: int = 0
    last_backfill_at: datetime | None = None
    backfill_status: str = "idle"
    backfill_started_at: datetime | None = None
    backfill_error: str | None = None
    updated_at: datetime


class TrackedProductDetailResponse(TrackedProductListItemResponse):
    latest_timeline_event: ProductTimelineEventResponse | None = None
    linked_news: list[ProductNewsItemResponse] = Field(default_factory=list)


class ProductTimelineResponse(BaseModel):
    product: TrackedProductListItemResponse
    items: list[ProductTimelineEventResponse] = Field(default_factory=list)


class ProductBackfillResponse(BaseModel):
    accepted: bool
    product_id: int
    product_slug: str
    fetched_candidates: int = 0
    linked_news_count: int = 0
    created_timeline_events: int = 0
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[TrackedProductListItemResponse]
