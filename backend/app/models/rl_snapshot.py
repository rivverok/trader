from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RLStateSnapshot(TimestampMixin, Base):
    """One row per evaluation timestep — captures the full state of the world."""

    __tablename__ = "rl_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    snapshot_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="daily_close"
    )  # daily_close, event, manual
    portfolio_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    market_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )


class RLStockSnapshot(TimestampMixin, Base):
    """One row per stock per evaluation timestep — per-stock features."""

    __tablename__ = "rl_stock_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rl_state_snapshots.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    price_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    technical_indicators: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ml_signal: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sentiment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    synthesis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analyst_input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    relative_strength: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
