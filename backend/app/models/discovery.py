"""Models for AI-driven stock discovery and watchlist management."""

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class WatchlistHint(TimestampMixin, Base):
    """User-provided hints/suggestions for the AI stock discovery engine."""

    __tablename__ = "watchlist_hints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hint_text: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryLog(TimestampMixin, Base):
    """Log of every AI watchlist decision with reasoning."""

    __tablename__ = "discovery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
