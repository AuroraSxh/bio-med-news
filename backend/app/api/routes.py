import hmac
import logging
from datetime import UTC, date, datetime
from threading import Lock
from typing import Annotated, Literal

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.categories import CATEGORIES
from app.core.config import get_settings
from app.db import get_db
from app.schemas.responses import (
    CategoriesResponse,
    CorporateCompanyEntry,
    CorporateDynamicsBuckets,
    CorporateDynamicsResponse,
    HealthResponse,
    ModelsResponse,
    NewsItemResponse,
    NewsListResponse,
    RefreshAcceptedResponse,
    TodaySummaryResponse,
)
from app.services.ingestion import run_ingestion_cycle
from app.services.news_repository import get_today_summary, list_news, list_news_for_summary, upsert_daily_summary
from app.schemas.products import (
    ProductBackfillResponse,
    ProductListResponse,
    ProductNewsItemResponse,
    ProductTimelineResponse,
    TrackedProductCreateRequest,
    TrackedProductDetailResponse,
)
from app.services.product_repository import (
    create_tracked_product,
    ensure_unique_slug,
    get_tracked_product_by_alnum_key,
    get_tracked_product_by_id,
    get_tracked_product_by_slug,
    get_tracked_product_detail,
    list_product_timeline,
    list_tracked_products,
)
from app.services.drug_aliases import _alnum_key as _alias_alnum_key, expand_aliases
from app.services.product_tracking import backfill_product_timeline, slugify_product_name

router = APIRouter(prefix="/api")
limiter = Limiter(key_func=get_remote_address)
_admin_refresh_lock = Lock()

AVAILABLE_MODELS = [
    {
        "id": "glm-5",
        "label": "GLM 5.0",
        "type": "文本生成",
        "description": "编程及智能体任务",
    },
    {
        "id": "deepseek-chat",
        "label": "DeepSeek V3.2",
        "type": "非思考模式",
        "description": "通用文本处理",
    },
    {
        "id": "deepseek-reasoner",
        "label": "DeepSeek V3.2 Reasoning",
        "type": "深度思考模式",
        "description": "复杂逻辑深度推理",
    },
    {
        "id": "minimax-m2.5",
        "label": "MiniMax M2.5",
        "type": "文本生成",
        "description": "通用文本处理",
    },
]


@router.get("/models", response_model=ModelsResponse)
def list_models(request: Request) -> ModelsResponse:
    settings = get_settings()
    return ModelsResponse(
        models=AVAILABLE_MODELS,
        current=settings.glm5_model_name,
    )


@router.get("/health", response_model=HealthResponse)
def health(request: Request, db: Annotated[Session, Depends(get_db)], response: Response) -> HealthResponse:
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        service="backend",
        environment=get_settings().app_env,
        time=datetime.now(UTC),
        database=database_status,
    )


@router.get("/categories", response_model=CategoriesResponse)
@limiter.limit("60/minute")
def categories(request: Request) -> CategoriesResponse:
    return CategoriesResponse(categories=CATEGORIES)


@router.get("/news", response_model=NewsListResponse)
@limiter.limit("60/minute")
def news(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    category: Annotated[str | None, Query()] = None,
    report_date: Annotated[date | None, Query(alias="date")] = None,
    q: Annotated[str | None, Query(min_length=1)] = None,
    sort: Literal["published_at_desc", "published_at_asc"] = "published_at_desc",
) -> NewsListResponse:
    if category is not None and category not in CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_category",
                    "message": "Unsupported category value.",
                }
            },
        )

    return list_news(
        db=db,
        page=page,
        page_size=page_size,
        category=category,
        report_date=report_date,
        q=q,
        sort=sort,
    )


@router.get("/news/today-summary", response_model=TodaySummaryResponse)
@limiter.limit("60/minute")
def today_summary(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    report_date: Annotated[date | None, Query(alias="date")] = None,
) -> TodaySummaryResponse:
    return get_today_summary(db=db, report_date=report_date)


@router.get("/products", response_model=ProductListResponse)
@limiter.limit("60/minute")
def products(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(min_length=1)] = None,
) -> ProductListResponse:
    return ProductListResponse(items=list_tracked_products(db, q=q))


@router.post("/products", response_model=TrackedProductDetailResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_product(
    request: Request,
    payload: TrackedProductCreateRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> TrackedProductDetailResponse:
    from app.services.product_tracking import run_backfill_in_background

    # Expand aliases via known synonym registry (also handles case/hyphen
    # normalization for deduping). The expanded list is what gets persisted.
    # If the static registry returns little, fall back to LLM-based alias
    # discovery so uncommon / pre-approval codes still benefit from common
    # alias coverage. LLM failures must never break product creation.
    glm5_for_aliases = None
    try:
        from app.services.glm5_client import GLM5Client

        candidate = GLM5Client()
        if candidate.is_configured:
            glm5_for_aliases = candidate
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not instantiate GLM5Client for alias discovery: %s", exc)

    try:
        expanded_aliases = expand_aliases(
            payload.display_name,
            list(payload.aliases or []),
            glm5_client=glm5_for_aliases,
            company_name=payload.company_name,
            indications=list(payload.indications or []),
            modality=payload.modality,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LLM-augmented alias expansion failed; falling back to static: %s", exc)
        expanded_aliases = expand_aliases(payload.display_name, list(payload.aliases or []))

    # Collision check: refuse to create a duplicate when any alias (expanded
    # or original display name) already exists on another tracked product.
    keys_to_check: list[str] = []
    seen_keys: set[str] = set()
    for name in [payload.display_name, *expanded_aliases]:
        k = _alias_alnum_key(name)
        if k and k not in seen_keys:
            seen_keys.add(k)
            keys_to_check.append(k)
    for key in keys_to_check:
        existing = get_tracked_product_by_alnum_key(db, key)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "duplicate_product",
                        "message": f"Already tracking {existing.display_name} under slug {existing.slug}",
                    }
                },
            )

    # Swap in the expanded aliases before persistence.
    payload = payload.model_copy(update={"aliases": expanded_aliases})

    slug = ensure_unique_slug(db, payload.display_name, slugify_product_name)
    product = create_tracked_product(db, payload, slug)
    product.backfill_status = "running"
    product.backfill_started_at = datetime.now(UTC)
    product.backfill_error = None
    db.commit()
    background_tasks.add_task(run_backfill_in_background, product.id)
    detail = get_tracked_product_detail(db, product.slug)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load product detail.")
    return detail


@router.get("/products/{slug}", response_model=TrackedProductDetailResponse)
@limiter.limit("60/minute")
def product_detail(
    request: Request,
    slug: str,
    db: Annotated[Session, Depends(get_db)],
) -> TrackedProductDetailResponse:
    detail = get_tracked_product_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked product not found.")
    return detail


@router.get("/products/{slug}/timeline", response_model=ProductTimelineResponse)
@limiter.limit("60/minute")
def product_timeline(
    request: Request,
    slug: str,
    db: Annotated[Session, Depends(get_db)],
) -> ProductTimelineResponse:
    response = list_product_timeline(db, slug)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked product not found.")
    return response


@router.get("/products/{slug}/sources", response_model=list[ProductNewsItemResponse])
@limiter.limit("60/minute")
def product_sources(
    request: Request,
    slug: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[ProductNewsItemResponse]:
    detail = get_tracked_product_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked product not found.")
    return detail.linked_news


@router.post(
    "/products/{product_id}/backfill",
    response_model=ProductBackfillResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
def product_backfill(
    request: Request,
    product_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
) -> ProductBackfillResponse:
    from app.services.product_tracking import run_backfill_in_background

    product = get_tracked_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked product not found.")

    now = datetime.now(UTC)
    stale_threshold_minutes = 15
    started = product.backfill_started_at
    if product.backfill_status == "running" and started is not None:
        # Treat as stale after threshold, otherwise reject.
        age_minutes = (now - started).total_seconds() / 60
        if age_minutes < stale_threshold_minutes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Backfill already running for this product.",
            )

    product.backfill_status = "running"
    product.backfill_started_at = now
    product.backfill_error = None
    db.commit()

    background_tasks.add_task(run_backfill_in_background, product.id)

    return ProductBackfillResponse(
        accepted=True,
        product_id=product.id,
        product_slug=product.slug,
        fetched_candidates=0,
        linked_news_count=0,
        created_timeline_events=0,
        updated_at=now,
    )


@router.delete("/products/{product_id}", status_code=204)
@limiter.limit("5/minute")
def delete_product(
    request: Request,
    product_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    product = get_tracked_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked product not found.")
    db.delete(product)
    db.commit()
    return Response(status_code=204)


@router.post("/summary/regenerate", response_model=TodaySummaryResponse)
@limiter.limit("3/minute")
def regenerate_summary(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    model: Annotated[str | None, Query()] = None,
    report_date: Annotated[date | None, Query(alias="date")] = None,
) -> TodaySummaryResponse:
    from app.services.glm5_client import GLM5Client
    from app.services.summary import generate_daily_summary

    summary_date = report_date or datetime.now(UTC).date()
    items = list_news_for_summary(db, summary_date)

    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "no_items",
                    "message": "No news items available for summary generation.",
                }
            },
        )

    glm5 = GLM5Client() if model else None
    # Invariant: regenerate_summary MUST NOT mutate rows in `news_items`.
    # It only reads news (list_news_for_summary), invokes the LLM to produce
    # a DailySummaryDraft, and writes to `daily_summaries` via upsert.
    # Any re-classification logic belongs in the ingestion pipeline, not here.
    summary, model_name = generate_daily_summary(items, summary_date, glm5=glm5, model_name=model)

    if summary is not None:
        upsert_daily_summary(db, summary_date, summary, model_name=model_name)

    return get_today_summary(db, summary_date)


@router.post(
    "/admin/refresh",
    response_model=RefreshAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
def admin_refresh(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> RefreshAcceptedResponse:
    configured_token = get_settings().admin_refresh_token
    if not configured_token or configured_token == "change_me":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "service_unavailable",
                    "message": "Admin refresh token is not configured.",
                }
            },
        )
    if not hmac.compare_digest(x_admin_token or "", configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "unauthorized",
                    "message": "Invalid admin token.",
                }
            },
        )

    if not _admin_refresh_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "refresh_already_running",
                    "message": "A manual refresh is already running in this backend process.",
                }
            },
        )

    try:
        result = run_ingestion_cycle(db, trigger="admin_refresh")
    finally:
        _admin_refresh_lock.release()
    return RefreshAcceptedResponse(
        accepted=True,
        message=(
            "Refresh completed. "
            f"Fetched {result.fetched_count}, inserted {result.inserted_count}, "
            f"updated {result.updated_count}, duplicates {result.duplicate_count}."
        ),
        requested_at=datetime.now(UTC),
    )


@router.get("/corporate-dynamics", response_model=CorporateDynamicsResponse)
@limiter.limit("60/minute")
def corporate_dynamics(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signal: Annotated[str | None, Query()] = None,
    company: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 40,
) -> CorporateDynamicsResponse:
    """Aggregate corporate signals (layoffs / new pipeline / financing) per
    curated cell-therapy company by scanning persisted news_items at query
    time. Computed in-process so it does not depend on a re-enrich pass
    having populated the news_items.company_name/corporate_signals columns.
    """
    from app.models import NewsItem
    from app.services.corporate_dynamics import (
        CELL_THERAPY_COMPANIES,
        CORPORATE_SIGNAL_RULES,
        detect_corporate_signals,
        get_company,
        match_company,
    )
    from sqlalchemy import select as _select

    if signal is not None and signal not in CORPORATE_SIGNAL_RULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_signal", "message": f"Unknown signal: {signal}"}},
        )

    # Pull a recent slice ordered by published_at desc. We keep the window
    # wide enough (up to 2000) so per-company buckets have material to slice.
    rows = db.scalars(
        _select(NewsItem)
        .order_by(NewsItem.published_at.desc())
        .limit(2000)
    ).all()

    # company_name -> { bucket -> [NewsItemResponse,...] }
    buckets_by_company: dict[str, dict[str, list[NewsItemResponse]]] = {}
    last_ts_by_company: dict[str, datetime] = {}

    for row in rows:
        text_blob = " ".join(filter(None, [row.title or "", row.short_summary or "", row.content_text or ""]))
        # Prefer persisted tags if present, else compute on the fly.
        row_company = getattr(row, "company_name", None) or match_company(text_blob)
        if not row_company:
            continue
        if company is not None and row_company != company:
            continue

        row_signals = getattr(row, "corporate_signals", None) or detect_corporate_signals(text_blob)
        if not row_signals:
            continue
        if signal is not None and signal not in row_signals:
            continue

        entry = buckets_by_company.setdefault(row_company, {k: [] for k in CORPORATE_SIGNAL_RULES})
        item_resp = NewsItemResponse.model_validate(row)
        for bucket in row_signals:
            if signal is not None and bucket != signal:
                continue
            if bucket not in entry:
                continue
            if len(entry[bucket]) >= limit:
                continue
            entry[bucket].append(item_resp)

        pub = row.published_at
        if pub is not None and (row_company not in last_ts_by_company or pub > last_ts_by_company[row_company]):
            last_ts_by_company[row_company] = pub

    # Build response sorted by most-recent signal timestamp desc.
    entries: list[CorporateCompanyEntry] = []
    for company_name, buckets in buckets_by_company.items():
        meta = get_company(company_name) or {}
        if not any(buckets.values()):
            continue
        entries.append(
            CorporateCompanyEntry(
                name=company_name,
                chinese_name=meta.get("chinese_name", "") or company_name,
                signals=CorporateDynamicsBuckets(**buckets),
                last_updated_at=last_ts_by_company.get(company_name),
            )
        )
    entries.sort(key=lambda e: e.last_updated_at or datetime.min.replace(tzinfo=UTC), reverse=True)

    return CorporateDynamicsResponse(companies=entries, total_companies=len(entries))
