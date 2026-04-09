"""add economic_indicators and sec_filings tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── economic_indicators ──
    op.create_table(
        "economic_indicators",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("indicator_code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="FRED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_economic_indicators_code", "economic_indicators", ["indicator_code"])
    op.create_index(
        "ix_economic_indicators_code_date",
        "economic_indicators",
        ["indicator_code", "date"],
        unique=True,
    )

    # ── sec_filings ──
    op.create_table(
        "sec_filings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("filing_type", sa.String(20), nullable=False),
        sa.Column("filed_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accession_number", sa.String(30), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("analyzed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accession_number"),
    )
    op.create_index("ix_sec_filings_stock_id", "sec_filings", ["stock_id"])


def downgrade() -> None:
    op.drop_table("sec_filings")
    op.drop_table("economic_indicators")
