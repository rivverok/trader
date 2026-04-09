"""add analysis tables (news_analyses, filing_analyses, context_syntheses, claude_usage)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── news_analyses ──
    op.create_table(
        "news_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("news_articles.id"), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("impact_severity", sa.String(20), nullable=False),
        sa.Column("material_event", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("key_entities", JSONB(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("claude_model_used", sa.String(60), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id"),
    )

    # ── filing_analyses ──
    op.create_table(
        "filing_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("sec_filings.id"), nullable=False),
        sa.Column("revenue_trend", sa.String(50), nullable=True),
        sa.Column("margin_analysis", sa.Text(), nullable=True),
        sa.Column("risk_changes", sa.Text(), nullable=True),
        sa.Column("guidance_sentiment", sa.Float(), nullable=True),
        sa.Column("key_findings", JSONB(), nullable=True),
        sa.Column("claude_model_used", sa.String(60), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filing_id"),
    )

    # ── context_syntheses ──
    op.create_table(
        "context_syntheses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("overall_sentiment", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("key_factors", JSONB(), nullable=True),
        sa.Column("risks", JSONB(), nullable=True),
        sa.Column("opportunities", JSONB(), nullable=True),
        sa.Column("reasoning_chain", sa.Text(), nullable=True),
        sa.Column("claude_model_used", sa.String(60), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_syntheses_stock_id", "context_syntheses", ["stock_id"])

    # ── claude_usage ──
    op.create_table(
        "claude_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claude_usage_date", "claude_usage", ["date"])


def downgrade() -> None:
    op.drop_table("claude_usage")
    op.drop_table("context_syntheses")
    op.drop_table("filing_analyses")
    op.drop_table("news_analyses")
