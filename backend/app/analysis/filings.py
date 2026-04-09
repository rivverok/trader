"""SEC filing analysis using Claude API."""

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.models.analysis import FilingAnalysis
from app.models.sec_filing import SecFiling

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("filings")


async def analyze_pending_filings(db_session: AsyncSession) -> dict[str, Any]:
    """Analyze all un-analyzed SEC filings.

    Uses Sonnet (smart model) for filings since they require deeper analysis.
    Processes one filing at a time because they're large and complex.
    """
    result = await db_session.execute(
        select(SecFiling)
        .where(SecFiling.analyzed.is_(False))
        .where(SecFiling.raw_content.isnot(None))
        .order_by(SecFiling.filed_date.desc())
        .limit(10)
    )
    filings = list(result.scalars().all())

    if not filings:
        return {"status": "skip", "reason": "no pending filings with content"}

    total_analyzed = 0
    errors = 0

    for filing in filings:
        try:
            await _analyze_filing(db_session, filing)
            total_analyzed += 1
        except Exception as e:
            logger.error("Filing analysis failed for %s: %s", filing.accession_number, e)
            errors += 1
            # Mark as analyzed to avoid blocking the queue
            await db_session.execute(
                update(SecFiling)
                .where(SecFiling.id == filing.id)
                .values(analyzed=True)
            )
            await db_session.commit()

    return {
        "status": "ok",
        "filings_analyzed": total_analyzed,
        "errors": errors,
    }


async def _analyze_filing(db_session: AsyncSession, filing: SecFiling) -> None:
    """Send a single filing to Claude and store the result."""
    # Truncate very long filing content to fit context window
    content = filing.raw_content or ""
    if len(content) > 100_000:
        # Take first 50K and last 50K (intro + financials + risk factors at end)
        content = content[:50_000] + "\n\n[...TRUNCATED...]\n\n" + content[-50_000:]

    user_message = (
        f"Filing Type: {filing.filing_type}\n"
        f"Filed Date: {filing.filed_date.strftime('%Y-%m-%d')}\n"
        f"Accession Number: {filing.accession_number}\n\n"
        f"Filing Content:\n{content}"
    )

    data = await call_claude(
        db_session=db_session,
        task_type="filing",
        user_message=user_message,
        system_prompt=SYSTEM_PROMPT,
        model=settings.CLAUDE_MODEL_SMART,
        max_tokens=4096,
    )

    filing_analysis = FilingAnalysis(
        filing_id=filing.id,
        revenue_trend=data.get("revenue_trend"),
        margin_analysis=data.get("margin_analysis"),
        risk_changes=data.get("risk_changes"),
        guidance_sentiment=(
            float(data["guidance_sentiment"])
            if data.get("guidance_sentiment") is not None
            else None
        ),
        key_findings=data.get("key_findings"),
        claude_model_used=settings.CLAUDE_MODEL_SMART,
        tokens_used=0,
    )
    db_session.add(filing_analysis)

    # Mark filing as analyzed
    await db_session.execute(
        update(SecFiling)
        .where(SecFiling.id == filing.id)
        .values(analyzed=True)
    )
    await db_session.commit()
