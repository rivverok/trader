from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class SecFiling(TimestampMixin, Base):
    __tablename__ = "sec_filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    filing_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 10-K, 10-Q, 8-K
    filed_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
