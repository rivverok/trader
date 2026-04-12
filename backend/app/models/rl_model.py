from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RLModel(TimestampMixin, Base):
    """Registry of uploaded RL models (ONNX files) for inference."""

    __tablename__ = "rl_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(20), nullable=False)  # PPO, DQN, SAC
    onnx_path: Mapped[str] = mapped_column(String(255), nullable=False)
    state_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    action_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    training_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    backtest_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
