"""add decision engine tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── risk_state (singleton config + runtime) ──
    op.create_table(
        "risk_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        # Configurable limits
        sa.Column("max_trade_dollars", sa.Float(), nullable=False, server_default="1000"),
        sa.Column("max_position_pct", sa.Float(), nullable=False, server_default="10"),
        sa.Column("max_sector_pct", sa.Float(), nullable=False, server_default="25"),
        sa.Column("daily_loss_limit", sa.Float(), nullable=False, server_default="500"),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=False, server_default="15"),
        sa.Column("min_confidence", sa.Float(), nullable=False, server_default="0.6"),
        # Runtime state
        sa.Column("trading_halted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("halt_reason", sa.Text(), nullable=True),
        sa.Column("halted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_realized_loss", sa.Float(), nullable=False, server_default="0"),
        sa.Column("portfolio_peak_value", sa.Float(), nullable=False, server_default="100000"),
        sa.Column("last_reset_date", sa.Date(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed the singleton row with defaults
    op.execute(
        "INSERT INTO risk_state (id, max_trade_dollars, max_position_pct, max_sector_pct, "
        "daily_loss_limit, max_drawdown_pct, min_confidence, trading_halted, daily_realized_loss, "
        "portfolio_peak_value) VALUES (1, 1000, 10, 25, 500, 15, 0.6, false, 0, 100000)"
    )

    # ── Add FK columns to proposed_trades ──
    op.add_column(
        "proposed_trades",
        sa.Column("synthesis_id", sa.Integer(), sa.ForeignKey("context_syntheses.id"), nullable=True),
    )
    op.add_column(
        "proposed_trades",
        sa.Column("analyst_input_id", sa.Integer(), sa.ForeignKey("analyst_inputs.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proposed_trades", "analyst_input_id")
    op.drop_column("proposed_trades", "synthesis_id")
    op.drop_table("risk_state")
