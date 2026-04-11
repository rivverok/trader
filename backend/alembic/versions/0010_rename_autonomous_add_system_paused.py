"""Rename autonomous_mode to growth_mode, add system_paused column.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("risk_state", "autonomous_mode", new_column_name="growth_mode")
    op.add_column(
        "risk_state",
        sa.Column("system_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("risk_state", "system_paused")
    op.alter_column("risk_state", "growth_mode", new_column_name="autonomous_mode")
