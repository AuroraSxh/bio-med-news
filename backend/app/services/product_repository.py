import re
from datetime import UTC, datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import NewsItem, ProductNewsLink, ProductTimelineEvent, TrackedProduct
from app.services.drug_aliases import _alnum_key as _alias_alnum_key
from app.schemas.products import (
    ProductNewsItemResponse,
    ProductTimelineEventResponse,
    ProductTimelineResponse,
    TrackedProductCreateRequest,
    TrackedProductDetailResponse,
    TrackedProductListItemResponse,
)


def create_tracked_product(db: Session, payload: TrackedProductCreateRequest, slug: str) -> TrackedProduct:
    product = TrackedProduct(
        slug=slug,
        display_name=payload.display_name,
        company_name=payload.company_name,
        aliases=payload.aliases,
        indications=payload.indications,
        modality=payload.modality,
        status="active",
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def list_tracked_products(db: Session, q: str | None = None) -> list[TrackedProductListItemResponse]:
    query: Select[tuple[TrackedProduct]] = select(TrackedProduct).order_by(TrackedProduct.updated_at.desc(), TrackedProduct.id.desc())
    products = db.scalars(query).all()
    if q and q.strip():
        # Token-level alnum-normalized substring match against display_name +
        # company_name + aliases. This lets users find "AZD-0120" by typing
        # "azd0120", "Abecma" by typing "abecma", etc.
        tokens = [tok for tok in re.split(r"\s+", q.strip()) if tok]
        token_keys = [k for k in (_alias_alnum_key(tok) for tok in tokens) if k]
        if token_keys:
            def _matches(product: TrackedProduct) -> bool:
                haystack_parts = [product.display_name or "", product.company_name or ""]
                haystack_parts.extend(product.aliases or [])
                hay_key = _alias_alnum_key(" ".join(haystack_parts))
                return any(tk in hay_key for tk in token_keys)

            products = [p for p in products if _matches(p)]
    return [_product_list_item(db, product) for product in products]


def get_tracked_product_by_alnum_key(db: Session, key: str) -> TrackedProduct | None:
    """Return the first TrackedProduct whose display_name/company_name/aliases
    contain any entry matching the provided alnum-normalized key."""
    if not key:
        return None
    for product in db.scalars(select(TrackedProduct)).all():
        candidates: list[str] = []
        if product.display_name:
            candidates.append(product.display_name)
        if product.aliases:
            candidates.extend(product.aliases)
        for name in candidates:
            if _alias_alnum_key(name) == key:
                return product
    return None


def get_tracked_product_by_slug(db: Session, slug: str) -> TrackedProduct | None:
    return db.scalar(select(TrackedProduct).where(TrackedProduct.slug == slug).limit(1))


def get_tracked_product_by_id(db: Session, product_id: int) -> TrackedProduct | None:
    return db.scalar(select(TrackedProduct).where(TrackedProduct.id == product_id).limit(1))


def get_tracked_product_detail(db: Session, slug: str) -> TrackedProductDetailResponse | None:
    product = get_tracked_product_by_slug(db, slug)
    if product is None:
        return None
    list_item = _product_list_item(db, product)
    latest_event = db.scalar(
        select(ProductTimelineEvent)
        .where(ProductTimelineEvent.product_id == product.id)
        .order_by(ProductTimelineEvent.event_date.desc(), ProductTimelineEvent.id.desc())
        .limit(1)
    )
    linked_news_rows = db.execute(
        select(ProductNewsLink, NewsItem)
        .join(NewsItem, ProductNewsLink.news_item_id == NewsItem.id)
        .where(ProductNewsLink.product_id == product.id)
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(12)
    ).all()
    linked_news = [
        ProductNewsItemResponse(
            id=item.id,
            title=item.title,
            canonical_url=item.canonical_url,
            source_name=item.source_name,
            published_at=item.published_at,
            category=item.category,
            short_summary=item.short_summary,
            match_source=link.match_source,
            match_confidence=link.match_confidence,
        )
        for link, item in linked_news_rows
    ]
    return TrackedProductDetailResponse(
        **list_item.model_dump(),
        latest_timeline_event=_timeline_response(latest_event) if latest_event else None,
        linked_news=linked_news,
    )


def list_product_timeline(db: Session, slug: str) -> ProductTimelineResponse | None:
    product = get_tracked_product_by_slug(db, slug)
    if product is None:
        return None
    events = db.scalars(
        select(ProductTimelineEvent)
        .where(ProductTimelineEvent.product_id == product.id)
        .order_by(ProductTimelineEvent.event_date.asc(), ProductTimelineEvent.id.asc())
    ).all()
    return ProductTimelineResponse(
        product=_product_list_item(db, product),
        items=[_timeline_response(event) for event in events],
    )


def search_news_candidates_for_product(db: Session, terms: list[str], limit: int = 80) -> list[NewsItem]:
    import re as _re

    cleaned_terms = [term.strip() for term in terms if term and term.strip()]
    if not cleaned_terms:
        return []
    variants: list[str] = []
    seen: set[str] = set()
    for term in cleaned_terms[:8]:
        for candidate in (term, _re.sub(r"[^A-Za-z0-9]+", "", term)):
            key = candidate.casefold()
            if candidate and len(candidate) >= 3 and key not in seen:
                seen.add(key)
                variants.append(candidate)
    filters = []
    for term in variants:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        needle = f"%{escaped}%"
        filters.append(NewsItem.title.ilike(needle, escape="\\"))
        filters.append(NewsItem.short_summary.ilike(needle, escape="\\"))
        filters.append(NewsItem.content_text.ilike(needle, escape="\\"))
    return db.scalars(
        select(NewsItem)
        .where(or_(*filters))
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
    ).all()


def upsert_product_news_link(
    db: Session,
    product_id: int,
    news_item_id: int,
    match_source: str,
    match_confidence: float | None,
) -> ProductNewsLink:
    existing = db.scalar(
        select(ProductNewsLink)
        .where(ProductNewsLink.product_id == product_id, ProductNewsLink.news_item_id == news_item_id)
        .limit(1)
    )
    if existing is None:
        existing = ProductNewsLink(
            product_id=product_id,
            news_item_id=news_item_id,
            match_source=match_source,
            match_confidence=match_confidence,
        )
        db.add(existing)
    else:
        existing.match_source = match_source
        existing.match_confidence = match_confidence
    db.flush()
    return existing


def list_linked_news_for_product(db: Session, product_id: int) -> list[NewsItem]:
    return db.scalars(
        select(NewsItem)
        .join(ProductNewsLink, ProductNewsLink.news_item_id == NewsItem.id)
        .where(ProductNewsLink.product_id == product_id)
        .order_by(NewsItem.published_at.asc(), NewsItem.id.asc())
    ).all()


def upsert_product_timeline_event(
    db: Session,
    *,
    product_id: int,
    event_date: datetime,
    event_date_precision: str,
    milestone_type: str,
    milestone_label: str,
    phase_label: str | None,
    headline: str,
    event_summary: str,
    indication: str | None,
    region: str | None,
    confidence: float | None,
    evidence_news_item_ids: list[int],
    evidence_urls: list[str],
    event_hash: str,
) -> ProductTimelineEvent:
    existing = db.scalar(
        select(ProductTimelineEvent)
        .where(ProductTimelineEvent.product_id == product_id, ProductTimelineEvent.event_hash == event_hash)
        .limit(1)
    )
    values = {
        "event_date": event_date,
        "event_date_precision": event_date_precision,
        "milestone_type": milestone_type,
        "milestone_label": milestone_label,
        "phase_label": phase_label,
        "headline": headline,
        "event_summary": event_summary,
        "indication": indication,
        "region": region,
        "confidence": confidence,
        "evidence_news_item_ids": evidence_news_item_ids,
        "evidence_urls": evidence_urls,
        "event_hash": event_hash,
    }
    if existing is None:
        existing = ProductTimelineEvent(product_id=product_id, **values)
        db.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    db.flush()
    return existing


def mark_product_backfilled(db: Session, product: TrackedProduct) -> None:
    product.last_backfill_at = datetime.now(UTC)
    db.commit()
    db.refresh(product)


def ensure_unique_slug(db: Session, display_name: str, slugify_fn) -> str:
    base_slug = slugify_fn(display_name)
    slug = base_slug
    suffix = 2
    while db.scalar(select(TrackedProduct.id).where(TrackedProduct.slug == slug).limit(1)) is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _product_list_item(db: Session, product: TrackedProduct) -> TrackedProductListItemResponse:
    timeline_count = db.scalar(
        select(func.count()).select_from(ProductTimelineEvent).where(ProductTimelineEvent.product_id == product.id)
    ) or 0
    linked_count = db.scalar(
        select(func.count()).select_from(ProductNewsLink).where(ProductNewsLink.product_id == product.id)
    ) or 0
    return TrackedProductListItemResponse(
        id=product.id,
        slug=product.slug,
        display_name=product.display_name,
        company_name=product.company_name,
        aliases=product.aliases or [],
        indications=product.indications or [],
        modality=product.modality,
        status=product.status,
        timeline_event_count=int(timeline_count),
        linked_news_count=int(linked_count),
        last_backfill_at=product.last_backfill_at,
        backfill_status=getattr(product, "backfill_status", "idle") or "idle",
        backfill_started_at=getattr(product, "backfill_started_at", None),
        backfill_error=getattr(product, "backfill_error", None),
        updated_at=product.updated_at,
    )


def _timeline_response(event: ProductTimelineEvent) -> ProductTimelineEventResponse:
    return ProductTimelineEventResponse(
        id=event.id,
        event_date=event.event_date,
        event_date_precision=event.event_date_precision,
        milestone_type=event.milestone_type,
        milestone_label=event.milestone_label,
        phase_label=event.phase_label,
        headline=event.headline,
        event_summary=event.event_summary,
        indication=event.indication,
        region=event.region,
        confidence=event.confidence,
        evidence_news_item_ids=event.evidence_news_item_ids or [],
        evidence_urls=event.evidence_urls or [],
    )
