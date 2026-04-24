from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")


class TrackedProduct(Base):
    __tablename__ = "tracked_products"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tracked_products_slug"),
        Index("ix_tracked_products_display_name", "display_name"),
        Index("ix_tracked_products_company_name", "company_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    indications: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    modality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_backfill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backfill_status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle", server_default="idle")
    backfill_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backfill_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    backfill_last_result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    news_links = relationship("ProductNewsLink", back_populates="product", cascade="all, delete-orphan")
    timeline_events = relationship("ProductTimelineEvent", back_populates="product", cascade="all, delete-orphan")


class ProductNewsLink(Base):
    __tablename__ = "product_news_links"
    __table_args__ = (
        UniqueConstraint("product_id", "news_item_id", name="uq_product_news_links_product_news"),
        Index("ix_product_news_links_product_id", "product_id"),
        Index("ix_product_news_links_news_item_id", "news_item_id"),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_product_news_links_match_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("tracked_products.id", ondelete="CASCADE"), nullable=False)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False)
    match_source: Mapped[str] = mapped_column(String(40), nullable=False, default="keyword")
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    product = relationship("TrackedProduct", back_populates="news_links")


class ProductTimelineEvent(Base):
    __tablename__ = "product_timeline_events"
    __table_args__ = (
        UniqueConstraint("product_id", "event_hash", name="uq_product_timeline_events_product_hash"),
        Index("ix_product_timeline_events_product_date", "product_id", "event_date"),
        Index("ix_product_timeline_events_milestone_type", "milestone_type"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_product_timeline_events_confidence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("tracked_products.id", ondelete="CASCADE"), nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_date_precision: Mapped[str] = mapped_column(String(20), nullable=False, default="day")
    milestone_type: Mapped[str] = mapped_column(String(50), nullable=False)
    milestone_label: Mapped[str] = mapped_column(String(160), nullable=False)
    phase_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    event_summary: Mapped[str] = mapped_column(Text, nullable=False)
    indication: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_news_item_ids: Mapped[list[int]] = mapped_column(JSONType, nullable=False, default=list)
    evidence_urls: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    product = relationship("TrackedProduct", back_populates="timeline_events")
