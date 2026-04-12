"""Clean up stale 'Market closed' proposals.

The market hours check was removed from the risk manager — proposals can be
created anytime and execute when the market opens.  Old proposals that were
blocked solely because the market was closed should be promoted to 'proposed'
with risk_check_passed = True.
"""

from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    # Promote queued proposals that were only blocked by market hours
    op.execute("""
        UPDATE proposed_trades
        SET status = 'proposed',
            risk_check_passed = true,
            risk_check_reason = 'ok'
        WHERE status = 'queued'
          AND (
            risk_check_reason LIKE '%Market closed%'
            OR risk_check_reason LIKE '%market closed%'
            OR risk_check_reason LIKE '%weekend%'
          )
    """)


def downgrade() -> None:
    pass
