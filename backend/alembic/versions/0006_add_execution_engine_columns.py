"""add execution engine columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add auto_execute and trading_paused to risk_state
    op.add_column(
        "risk_state",
        sa.Column("auto_execute", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "risk_state",
        sa.Column("trading_paused", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("risk_state", "trading_paused")
    op.drop_column("risk_state", "auto_execute")
