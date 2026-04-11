from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RiskState(TimestampMixin, Base):
    """Singleton row: risk config + runtime state.

    Risk parameters are editable by the user via API/UI.
    trading_halted can only be cleared by the user (POST /api/risk/resume).
    """

    __tablename__ = "risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Configurable risk limits ──
    max_trade_dollars: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    max_position_pct: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    max_sector_pct: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    daily_loss_limit: Mapped[float] = mapped_column(Float, nullable=False, default=500.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=15.0)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)

    # ── System control flags ──
    auto_execute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    growth_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trading_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    system_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Runtime state ──
    trading_halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    halt_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    halted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_realized_loss: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    portfolio_peak_value: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    last_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
