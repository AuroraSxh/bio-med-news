from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


JSONType = JSON().with_variant(JSONB(), "postgresql")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_news_items_canonical_url"),
        Index("ix_news_items_published_at", "published_at"),
        Index("ix_news_items_category", "category"),
        Index("ix_news_items_title_hash", "title_hash"),
        CheckConstraint("importance_score IS NULL OR (importance_score >= 0 AND importance_score <= 1)", name="ck_news_items_importance_score"),
        CheckConstraint("relevance_to_cell_therapy IS NULL OR (relevance_to_cell_therapy >= 0 AND relevance_to_cell_therapy <= 1)", name="ck_news_items_relevance_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    short_summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True, default="en")
    title_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entities: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_to_cell_therapy: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Snapshot of feed visibility at first-ingest time. Re-enrichment or
    # summary regeneration must NEVER flip this back to False, so items
    # previously surfaced to users do not silently disappear when a stricter
    # model (e.g. a newly-selected summary model) demotes their category.
    visible_in_feed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("1"), default=True)
    # Corporate dynamics tagging (see app.services.corporate_dynamics).
    # Populated during enrichment; nullable for un-tagged / historical rows.
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    corporate_signals: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("summary_date", name="uq_daily_summaries_summary_date"),
        Index("ix_daily_summaries_summary_date", "summary_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_summary: Mapped[str] = mapped_column(Text, nullable=False)
    top_events: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    trend_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_counts: Mapped[dict[str, int]] = mapped_column(JSONType, nullable=False, default=dict)
    category_summaries: Mapped[dict[str, str] | None] = mapped_column(JSONType, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
