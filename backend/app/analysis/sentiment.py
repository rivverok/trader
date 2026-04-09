"""News sentiment analysis using Claude API."""

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import call_claude, load_prompt
from app.config import settings
from app.models.analysis import NewsAnalysis
from app.models.news import NewsArticle

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("sentiment")
BATCH_SIZE = 5  # Max articles per Claude call


async def analyze_pending_news(db_session: AsyncSession) -> dict[str, Any]:
    """Analyze all un-analyzed news articles.

    Batches up to BATCH_SIZE articles into a single Claude call for efficiency.
    Uses Haiku (fast/cheap model) for sentiment.
    """
    # Fetch un-analyzed articles
    result = await db_session.execute(
        select(NewsArticle)
        .where(NewsArticle.analyzed.is_(False))
        .order_by(NewsArticle.published_at.desc())
        .limit(50)  # Process at most 50 per run
    )
    articles = list(result.scalars().all())

    if not articles:
        return {"status": "skip", "reason": "no pending articles"}

    total_analyzed = 0
    errors = 0

    # Process in batches
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]
        try:
            await _analyze_batch(db_session, batch)
            total_analyzed += len(batch)
        except Exception as e:
            logger.error("Batch analysis failed: %s", e)
            errors += 1

    return {
        "status": "ok",
        "articles_analyzed": total_analyzed,
        "errors": errors,
    }


async def _analyze_batch(
    db_session: AsyncSession, articles: list[NewsArticle]
) -> None:
    """Send a batch of articles to Claude and store the results."""
    # Build the user message
    articles_text = []
    for idx, article in enumerate(articles, 1):
        text = f"Article {idx}:\n"
        text += f"Headline: {article.headline}\n"
        if article.summary:
            text += f"Summary: {article.summary}\n"
        if article.raw_content and len(article.raw_content) > 200:
            # Include first 2000 chars of raw content for context
            text += f"Content: {article.raw_content[:2000]}\n"
        articles_text.append(text)

    user_message = (
        f"Analyze the following {len(articles)} news article(s):\n\n"
        + "\n---\n".join(articles_text)
    )

    # Call Claude (Haiku for sentiment — fast and cheap)
    data = await call_claude(
        db_session=db_session,
        task_type="sentiment",
        user_message=user_message,
        system_prompt=SYSTEM_PROMPT,
        model=settings.CLAUDE_MODEL_FAST,
        max_tokens=2048,
    )

    analyses = data.get("analyses", [])

    # Match results back to articles (by index)
    for idx, article in enumerate(articles):
        if idx < len(analyses):
            analysis = analyses[idx]
            # Store the analysis
            news_analysis = NewsAnalysis(
                article_id=article.id,
                sentiment_score=float(analysis.get("sentiment_score", 0.0)),
                impact_severity=analysis.get("impact_severity", "low"),
                material_event=bool(analysis.get("material_event", False)),
                key_entities=analysis.get("key_entities"),
                summary=analysis.get("summary", ""),
                claude_model_used=settings.CLAUDE_MODEL_FAST,
                tokens_used=0,  # Tracked at the call level in claude_usage
            )
            db_session.add(news_analysis)

            # Update the article's sentiment_score and analyzed flag
            await db_session.execute(
                update(NewsArticle)
                .where(NewsArticle.id == article.id)
                .values(
                    sentiment_score=news_analysis.sentiment_score,
                    analyzed=True,
                )
            )
        else:
            # Still mark as analyzed to avoid re-processing
            await db_session.execute(
                update(NewsArticle)
                .where(NewsArticle.id == article.id)
                .values(analyzed=True)
            )
            logger.warning(
                "No analysis returned for article %d: %s",
                article.id, article.headline[:80],
            )

    await db_session.commit()
