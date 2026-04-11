"""Lower min_confidence default from 0.6 to 0.25.

AI now dynamically controls aggression via its confidence output.
min_confidence is just a garbage-signal safety floor.
"""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    # Update the existing singleton row and the column default
    op.execute("UPDATE risk_state SET min_confidence = 0.25 WHERE min_confidence = 0.6")
    op.alter_column(
        "risk_state",
        "min_confidence",
        server_default="0.25",
    )


def downgrade() -> None:
    op.execute("UPDATE risk_state SET min_confidence = 0.6 WHERE min_confidence = 0.25")
    op.alter_column(
        "risk_state",
        "min_confidence",
        server_default="0.6",
    )
