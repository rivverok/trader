"""Context synthesis — combines all signals into a per-stock holistic assessment."""

import logging
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.models.analysis import ContextSynthesis, NewsAnalysis
from app.models.analyst_input import AnalystInput
from app.models.economic import EconomicIndicator
from app.models.news import NewsArticle
from app.models.sec_filing import SecFiling
from app.models.analysis import FilingAnalysis
from app.models.stock import Stock

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("synthesis")


async def run_context_synthesis(db_session: AsyncSession) -> dict[str, Any]:
    """Run context synthesis for all watchlist stocks.

    Uses Sonnet (smart model) to combine news, filings, economic data,
    and analyst inputs into a single assessment per stock.
    """
    result = await db_session.execute(
        select(Stock).where(Stock.on_watchlist.is_(True))
    )
    stocks = list(result.scalars().all())

    if not stocks:
        return {"status": "skip", "reason": "no watchlist stocks"}

    total_synthesized = 0
    errors = 0

    for stock in stocks:
        try:
            await _synthesize_stock(db_session, stock)
            total_synthesized += 1
        except Exception as e:
            logger.error("Synthesis failed for %s: %s", stock.symbol, e)
            errors += 1

    return {
        "status": "ok",
        "stocks_synthesized": total_synthesized,
        "errors": errors,
    }


async def _synthesize_stock(db_session: AsyncSession, stock: Stock) -> None:
    """Build context and call Claude for a single stock synthesis."""
    sections = []

    # 1. Recent news sentiments (last 20 analyzed articles)
    news_data = await _get_recent_news_analyses(db_session, stock.id)
    if news_data:
        sections.append(f"## Recent News Sentiments for {stock.symbol}\n{news_data}")

    # 2. Latest SEC filing analysis
    filing_data = await _get_latest_filing_analysis(db_session, stock.id)
    if filing_data:
        sections.append(f"## SEC Filing Analysis\n{filing_data}")

    # 3. Economic indicators
    economic_data = await _get_economic_context(db_session)
    if economic_data:
        sections.append(f"## Economic Indicators\n{economic_data}")

    # 4. Personal analyst notes
    analyst_data = await _get_analyst_inputs(db_session, stock.id)
    if analyst_data:
        sections.append(f"## Personal Analyst Notes\n{analyst_data}")

    if not sections:
        logger.info("No data available for synthesis of %s, skipping", stock.symbol)
        return

    user_message = (
        f"Stock: {stock.symbol} ({stock.name or 'Unknown'})\n"
        f"Sector: {stock.sector or 'Unknown'}\n\n"
        + "\n\n".join(sections)
    )

    data = await call_claude(
        db_session=db_session,
        task_type="synthesis",
        user_message=user_message,
        system_prompt=SYSTEM_PROMPT,
        model=settings.CLAUDE_MODEL_SMART,
        max_tokens=4096,
    )

    synthesis = ContextSynthesis(
        stock_id=stock.id,
        overall_sentiment=float(data.get("overall_sentiment", 0.0)),
        confidence=float(data.get("confidence", 0.0)),
        key_factors=data.get("key_factors"),
        risks=data.get("risks"),
        opportunities=data.get("opportunities"),
        reasoning_chain=data.get("reasoning_chain"),
        claude_model_used=settings.CLAUDE_MODEL_SMART,
        tokens_used=0,
    )
    db_session.add(synthesis)
    await db_session.commit()


# ── Data gathering helpers ────────────────────────────────────────────


async def _get_recent_news_analyses(
    db_session: AsyncSession, stock_id: int
) -> str | None:
    """Get recent analyzed news for a stock as formatted text."""
    result = await db_session.execute(
        select(NewsArticle, NewsAnalysis)
        .join(NewsAnalysis, NewsAnalysis.article_id == NewsArticle.id)
        .where(NewsArticle.stock_id == stock_id)
        .order_by(desc(NewsArticle.published_at))
        .limit(20)
    )
    rows = result.all()
    if not rows:
        return None

    lines = []
    for article, analysis in rows:
        lines.append(
            f"- [{article.published_at.strftime('%Y-%m-%d')}] "
            f"Sentiment: {analysis.sentiment_score:+.2f} | "
            f"Impact: {analysis.impact_severity} | "
            f"Material: {'YES' if analysis.material_event else 'no'} | "
            f"{analysis.summary}"
        )
    return "\n".join(lines)


async def _get_latest_filing_analysis(
    db_session: AsyncSession, stock_id: int
) -> str | None:
    """Get the latest filing analysis for a stock."""
    result = await db_session.execute(
        select(SecFiling, FilingAnalysis)
        .join(FilingAnalysis, FilingAnalysis.filing_id == SecFiling.id)
        .where(SecFiling.stock_id == stock_id)
        .order_by(desc(SecFiling.filed_date))
        .limit(1)
    )
    row = result.first()
    if not row:
        return None

    filing, analysis = row
    parts = [f"Type: {filing.filing_type} | Filed: {filing.filed_date.strftime('%Y-%m-%d')}"]
    if analysis.revenue_trend:
        parts.append(f"Revenue Trend: {analysis.revenue_trend}")
    if analysis.margin_analysis:
        parts.append(f"Margins: {analysis.margin_analysis}")
    if analysis.risk_changes:
        parts.append(f"Risk Changes: {analysis.risk_changes}")
    if analysis.guidance_sentiment is not None:
        parts.append(f"Guidance Sentiment: {analysis.guidance_sentiment:+.2f}")
    if analysis.key_findings:
        for finding in analysis.key_findings:
            parts.append(f"  - {finding}")
    return "\n".join(parts)


async def _get_economic_context(db_session: AsyncSession) -> str | None:
    """Get latest value for each economic indicator."""
    from sqlalchemy import func

    subquery = (
        select(
            EconomicIndicator.indicator_code,
            func.max(EconomicIndicator.date).label("max_date"),
        )
        .group_by(EconomicIndicator.indicator_code)
        .subquery()
    )
    result = await db_session.execute(
        select(EconomicIndicator)
        .join(
            subquery,
            (EconomicIndicator.indicator_code == subquery.c.indicator_code)
            & (EconomicIndicator.date == subquery.c.max_date),
        )
    )
    indicators = result.scalars().all()
    if not indicators:
        return None

    lines = []
    for ind in indicators:
        lines.append(
            f"- {ind.name} ({ind.indicator_code}): {ind.value} "
            f"(as of {ind.date.strftime('%Y-%m-%d')})"
        )
    return "\n".join(lines)


async def _get_analyst_inputs(
    db_session: AsyncSession, stock_id: int
) -> str | None:
    """Get active analyst inputs for a stock."""
    result = await db_session.execute(
        select(AnalystInput)
        .where(AnalystInput.stock_id == stock_id, AnalystInput.is_active.is_(True))
        .order_by(desc(AnalystInput.created_at))
    )
    inputs = result.scalars().all()
    if not inputs:
        return None

    lines = []
    for inp in inputs:
        lines.append(
            f"- Conviction: {inp.conviction}/10 | "
            f"Override: {inp.override_flag} | "
            f"Horizon: {inp.time_horizon_days or '?'} days\n"
            f"  Thesis: {inp.thesis}"
        )
        if inp.catalysts:
            lines.append(f"  Catalysts: {inp.catalysts}")
    return "\n".join(lines)
