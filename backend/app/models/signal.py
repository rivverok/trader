from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class MLSignal(TimestampMixin, Base):
    __tablename__ = "ml_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    signal: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell, hold
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    feature_importances: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
