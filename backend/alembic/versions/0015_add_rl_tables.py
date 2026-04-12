"""Add RL model table and system_mode to risk_state."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    # ── Add system_mode to risk_state ────────────────────────────────
    op.add_column(
        "risk_state",
        sa.Column("system_mode", sa.String(20), nullable=False, server_default="data_collection"),
    )

    # ── rl_models ────────────────────────────────────────────────────
    op.create_table(
        "rl_models",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("algorithm", sa.String(20), nullable=False),
        sa.Column("onnx_path", sa.String(255), nullable=False),
        sa.Column("state_spec", JSONB, nullable=True),
        sa.Column("action_spec", JSONB, nullable=True),
        sa.Column("training_metadata", JSONB, nullable=True),
        sa.Column("backtest_metrics", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rl_models")
    op.drop_column("risk_state", "system_mode")
