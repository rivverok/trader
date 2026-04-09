from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class NewsAnalysis(TimestampMixin, Base):
    __tablename__ = "news_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("news_articles.id"), nullable=False, unique=True
    )
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    impact_severity: Mapped[str] = mapped_column(String(20), nullable=False)  # low, medium, high
    material_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    key_entities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    claude_model_used: Mapped[str] = mapped_column(String(60), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class FilingAnalysis(TimestampMixin, Base):
    __tablename__ = "filing_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sec_filings.id"), nullable=False, unique=True
    )
    revenue_trend: Mapped[str | None] = mapped_column(String(50), nullable=True)
    margin_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidance_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    key_findings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    claude_model_used: Mapped[str] = mapped_column(String(60), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ContextSynthesis(TimestampMixin, Base):
    __tablename__ = "context_syntheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id"), nullable=False, index=True
    )
    overall_sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    key_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    risks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    opportunities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reasoning_chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_model_used: Mapped[str] = mapped_column(String(60), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ClaudeUsage(Base):
    __tablename__ = "claude_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)  # sentiment, filing, synthesis
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
