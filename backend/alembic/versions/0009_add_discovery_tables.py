"""add discovery tables

Revision ID: 0009
Revises: 0008
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_hints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("hint_text", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("ai_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "discovery_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(50), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_log_batch_id", "discovery_log", ["batch_id"])
    op.create_index("ix_discovery_log_symbol", "discovery_log", ["symbol"])


def downgrade() -> None:
    op.drop_table("discovery_log")
    op.drop_table("watchlist_hints")
