"""Add RL tables (state snapshots, stock snapshots, models) and system_mode to risk_state."""

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

    # ── rl_state_snapshots ───────────────────────────────────────────
    op.create_table(
        "rl_state_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("snapshot_type", sa.String(20), nullable=False, server_default="daily_close"),
        sa.Column("portfolio_state", JSONB, nullable=False),
        sa.Column("market_state", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── rl_stock_snapshots ───────────────────────────────────────────
    op.create_table(
        "rl_stock_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_id", sa.Integer,
            sa.ForeignKey("rl_state_snapshots.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("symbol", sa.String(10), nullable=False, index=True),
        sa.Column("price_data", JSONB, nullable=False),
        sa.Column("technical_indicators", JSONB, nullable=True),
        sa.Column("ml_signal", JSONB, nullable=True),
        sa.Column("sentiment", JSONB, nullable=True),
        sa.Column("synthesis", JSONB, nullable=True),
        sa.Column("analyst_input", JSONB, nullable=True),
        sa.Column("relative_strength", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
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
    op.drop_table("rl_stock_snapshots")
    op.drop_table("rl_state_snapshots")
    op.drop_column("risk_state", "system_mode")
