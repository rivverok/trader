"""Add backtest_results and model_registry tables.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("symbols", sa.Text(), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_return", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=False),
        sa.Column("trades_count", sa.Integer(), nullable=False),
        sa.Column("benchmark_return", sa.Float(), nullable=True),
        sa.Column("report_json", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("training_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbols_trained", sa.Text(), nullable=False),
        sa.Column("feature_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_metrics", JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_index("ix_model_registry_active", "model_registry", ["model_name", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_model_registry_active", table_name="model_registry")
    op.drop_table("model_registry")
    op.drop_table("backtest_results")
