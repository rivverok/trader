"""Create system_kv table for key-value metadata storage."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.create_table(
        "system_kv",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("system_kv")
