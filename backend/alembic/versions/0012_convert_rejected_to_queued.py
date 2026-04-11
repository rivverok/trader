"""Convert existing risk-blocked 'rejected' proposals to 'queued'.

Only converts proposals that were system-rejected (risk_check_reason starts
with known system patterns). User-rejected proposals stay as 'rejected'.
"""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    # Convert system-rejected proposals to 'queued'
    # User-rejected ones (manual rejection) keep 'rejected' status
    op.execute("""
        UPDATE proposed_trades
        SET status = 'queued'
        WHERE status = 'rejected'
          AND risk_check_reason NOT LIKE 'Manually rejected%'
          AND risk_check_reason != 'Manually rejected by user'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE proposed_trades
        SET status = 'rejected'
        WHERE status = 'queued'
    """)
