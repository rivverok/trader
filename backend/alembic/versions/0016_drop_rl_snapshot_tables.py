"""Drop redundant rl_state_snapshots and rl_stock_snapshots tables.

Training data is now served directly from source tables via the /api/training endpoints.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.drop_table("rl_stock_snapshots")
    op.drop_table("rl_state_snapshots")


def downgrade() -> None:
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
