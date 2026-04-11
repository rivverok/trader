"""Claude API client wrapper with usage tracking and cost estimation."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis import ClaudeUsage

logger = logging.getLogger(__name__)

# Approximate pricing per 1M tokens (as of 2026)
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a system prompt from the prompts/ directory."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD from token counts."""
    pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})
    return (input_tokens * pricing["input"] / 1_000_000) + (
        output_tokens * pricing["output"] / 1_000_000
    )


async def call_claude(
    db_session: AsyncSession,
    task_type: str,
    user_message: str,
    system_prompt: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call Claude API, parse JSON response, and log usage.

    Returns the parsed JSON dict from Claude's response.
    Raises ValueError if response is not valid JSON.
    """
    model = model or settings.CLAUDE_MODEL_FAST

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_message}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    # Extract text content
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Track usage
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = _estimate_cost(model, input_tokens, output_tokens)

    usage = ClaudeUsage(
        date=datetime.now(timezone.utc),
        task_type=task_type,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
    )
    db_session.add(usage)
    await db_session.commit()

    logger.info(
        "Claude %s [%s]: %d in / %d out tokens ($%.4f)",
        task_type, model, input_tokens, output_tokens, cost,
    )

    # Parse JSON from response
    # Strip any markdown fences Claude might include
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` wrapper
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Claude returned invalid JSON for %s: %s", task_type, e)
        logger.debug("Raw response: %s", text[:500])
        raise ValueError(f"Claude returned invalid JSON: {e}") from e
