"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ── stocks ──
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("exchange", sa.String(20), nullable=True),
        sa.Column("on_watchlist", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index("ix_stocks_symbol", "stocks", ["symbol"])

    # ── prices ──
    op.create_table(
        "prices",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("interval", sa.String(10), nullable=False, server_default="1Day"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prices_stock_id", "prices", ["stock_id"])
    op.create_index("ix_prices_timestamp", "prices", ["timestamp"])
    op.create_index("ix_prices_stock_timestamp", "prices", ["stock_id", "timestamp"])

    # Convert prices to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('prices', 'timestamp', migrate_data => true, if_not_exists => true)")

    # ── news_articles ──
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=True),
        sa.Column("headline", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("analyzed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_news_articles_stock_id", "news_articles", ["stock_id"])

    # ── ml_signals ──
    op.create_table(
        "ml_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("signal", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("feature_importances", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ml_signals_stock_id", "ml_signals", ["stock_id"])

    # ── proposed_trades ──
    op.create_table(
        "proposed_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("price_target", sa.Float(), nullable=True),
        sa.Column("order_type", sa.String(20), nullable=False, server_default="market"),
        sa.Column("ml_signal_id", sa.Integer(), sa.ForeignKey("ml_signals.id"), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning_chain", sa.Text(), nullable=True),
        sa.Column("risk_check_passed", sa.Boolean(), nullable=True),
        sa.Column("risk_check_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposed_trades_stock_id", "proposed_trades", ["stock_id"])

    # ── trades ──
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("proposed_trade_id", sa.Integer(), sa.ForeignKey("proposed_trades.id"), nullable=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slippage", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("alpaca_order_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_stock_id", "trades", ["stock_id"])

    # ── portfolio_positions ──
    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("shares", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_cost_basis", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id"),
    )

    # ── portfolio_snapshots ──
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_value", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("positions_value", sa.Float(), nullable=False),
        sa.Column("daily_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cumulative_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_snapshots_timestamp", "portfolio_snapshots", ["timestamp"])

    # ── analyst_inputs ──
    op.create_table(
        "analyst_inputs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("conviction", sa.Integer(), nullable=False),
        sa.Column("time_horizon_days", sa.Integer(), nullable=True),
        sa.Column("catalysts", sa.Text(), nullable=True),
        sa.Column("override_flag", sa.String(20), nullable=False, server_default="none"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyst_inputs_stock_id", "analyst_inputs", ["stock_id"])


def downgrade() -> None:
    op.drop_table("analyst_inputs")
    op.drop_table("portfolio_snapshots")
    op.drop_table("portfolio_positions")
    op.drop_table("trades")
    op.drop_table("proposed_trades")
    op.drop_table("ml_signals")
    op.drop_table("news_articles")
    op.drop_table("prices")
    op.drop_table("stocks")
