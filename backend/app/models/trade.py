from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class ProposedTrade(TimestampMixin, Base):
    __tablename__ = "proposed_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    price_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, default="market")
    ml_signal_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ml_signals.id"), nullable=True)
    synthesis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("context_syntheses.id"), nullable=True)
    analyst_input_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("analyst_inputs.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning_chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_check_passed: Mapped[bool | None] = mapped_column(nullable=True)
    risk_check_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")  # proposed, queued, approved, rejected, executed, expired


class Trade(TimestampMixin, Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    proposed_trade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proposed_trades.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    slippage: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpaca_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, filled, partial, cancelled, rejected
