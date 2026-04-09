from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class AnalystInput(TimestampMixin, Base):
    __tablename__ = "analyst_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    conviction: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    time_horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catalysts: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_flag: Mapped[str] = mapped_column(String(20), nullable=False, default="none")  # none, avoid, boost
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
