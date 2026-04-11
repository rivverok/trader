"""Service Status API — check connectivity of all external services."""

import logging
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["status"])

_startup_time = time.time()


class ServiceCheck(BaseModel):
    name: str
    status: str  # "ok", "error", "not_configured"
    message: str
    details: dict | None = None


class ServiceStatusResponse(BaseModel):
    overall: str  # "ok", "degraded", "error"
    services: list[ServiceCheck]


async def _check_api_server() -> ServiceCheck:
    uptime_seconds = int(time.time() - _startup_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    uptime_str = " ".join(parts)
    return ServiceCheck(
        name="API Server",
        status="ok",
        message=f"FastAPI running — uptime {uptime_str}",
        details={"uptime_seconds": uptime_seconds},
    )


async def _check_postgres() -> ServiceCheck:
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT 1"))
            if result.scalar() == 1:
                return ServiceCheck(
                    name="PostgreSQL",
                    status="ok",
                    message=f"Connected to {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
                )
    except Exception as e:
        return ServiceCheck(name="PostgreSQL", status="error", message=str(e))
    return ServiceCheck(name="PostgreSQL", status="error", message="Unexpected result")


async def _check_redis() -> ServiceCheck:
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.get_redis_url(), socket_connect_timeout=2)
        if r.ping():
            info = r.info("server")
            r.close()
            return ServiceCheck(
                name="Redis",
                status="ok",
                message=f"Connected to {settings.REDIS_HOST}:{settings.REDIS_PORT}",
                details={"redis_version": info.get("redis_version", "unknown")},
            )
        r.close()
    except Exception as e:
        return ServiceCheck(name="Redis", status="error", message=str(e))
    return ServiceCheck(name="Redis", status="error", message="Ping failed")


async def _check_alpaca() -> ServiceCheck:
    if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
        return ServiceCheck(
            name="Alpaca (Broker)",
            status="not_configured",
            message="ALPACA_API_KEY / ALPACA_SECRET_KEY not set in .env",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{settings.ALPACA_BASE_URL}/v2/account",
                headers={
                    "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
                    "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            is_paper = "paper" in settings.ALPACA_BASE_URL
            return ServiceCheck(
                name="Alpaca (Broker)",
                status="ok",
                message=f"{'Paper' if is_paper else 'Live'} account — {data.get('status', 'unknown')}",
                details={
                    "account_status": data.get("status"),
                    "buying_power": data.get("buying_power"),
                    "portfolio_value": data.get("portfolio_value"),
                    "cash": data.get("cash"),
                    "equity": data.get("equity"),
                    "trading_blocked": data.get("trading_blocked"),
                    "account_blocked": data.get("account_blocked"),
                    "pattern_day_trader": data.get("pattern_day_trader"),
                    "mode": "paper" if is_paper else "live",
                },
            )
        elif resp.status_code == 401:
            return ServiceCheck(name="Alpaca (Broker)", status="error", message="Invalid API key — check credentials")
        else:
            return ServiceCheck(name="Alpaca (Broker)", status="error", message=f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        return ServiceCheck(name="Alpaca (Broker)", status="error", message=str(e))


async def _check_anthropic() -> ServiceCheck:
    if not settings.ANTHROPIC_API_KEY:
        return ServiceCheck(
            name="Claude AI (Anthropic)",
            status="not_configured",
            message="ANTHROPIC_API_KEY not set in .env",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
            )
        if resp.status_code == 200:
            return ServiceCheck(
                name="Claude AI (Anthropic)",
                status="ok",
                message=f"API key valid — models: {settings.CLAUDE_MODEL_FAST}, {settings.CLAUDE_MODEL_SMART}",
                details={
                    "model_fast": settings.CLAUDE_MODEL_FAST,
                    "model_smart": settings.CLAUDE_MODEL_SMART,
                },
            )
        elif resp.status_code == 401:
            return ServiceCheck(name="Claude AI (Anthropic)", status="error", message="Invalid API key")
        else:
            return ServiceCheck(name="Claude AI (Anthropic)", status="ok", message=f"API key set (HTTP {resp.status_code} on model list — key may still be valid)")
    except Exception as e:
        return ServiceCheck(name="Claude AI (Anthropic)", status="error", message=str(e))


async def _check_finnhub() -> ServiceCheck:
    if not settings.FINNHUB_API_KEY:
        return ServiceCheck(
            name="Finnhub (News)",
            status="not_configured",
            message="FINNHUB_API_KEY not set in .env",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": "AAPL", "token": settings.FINNHUB_API_KEY},
            )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("c", 0) > 0:
                return ServiceCheck(name="Finnhub (News)", status="ok", message="API key valid — data flowing")
            return ServiceCheck(name="Finnhub (News)", status="ok", message="Connected (market may be closed)")
        elif resp.status_code == 401:
            return ServiceCheck(name="Finnhub (News)", status="error", message="Invalid API key")
        else:
            return ServiceCheck(name="Finnhub (News)", status="error", message=f"HTTP {resp.status_code}")
    except Exception as e:
        return ServiceCheck(name="Finnhub (News)", status="error", message=str(e))


async def _check_fred() -> ServiceCheck:
    if not settings.FRED_API_KEY:
        return ServiceCheck(
            name="FRED (Economic Data)",
            status="not_configured",
            message="FRED_API_KEY not set in .env",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://api.stlouisfed.org/fred/series",
                params={"series_id": "GDP", "api_key": settings.FRED_API_KEY, "file_type": "json"},
            )
        if resp.status_code == 200:
            return ServiceCheck(name="FRED (Economic Data)", status="ok", message="API key valid")
        elif resp.status_code in (400, 401):
            return ServiceCheck(name="FRED (Economic Data)", status="error", message="Invalid API key")
        else:
            return ServiceCheck(name="FRED (Economic Data)", status="error", message=f"HTTP {resp.status_code}")
    except Exception as e:
        return ServiceCheck(name="FRED (Economic Data)", status="error", message=str(e))


async def _check_edgar() -> ServiceCheck:
    if not settings.SEC_EDGAR_USER_AGENT:
        return ServiceCheck(
            name="SEC EDGAR (Filings)",
            status="not_configured",
            message="SEC_EDGAR_USER_AGENT not set in .env (format: 'Name email@example.com')",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                "https://efts.sec.gov/LATEST/search-index?q=test&dateRange=custom&startdt=2024-01-01&enddt=2024-01-02",
                headers={"User-Agent": settings.SEC_EDGAR_USER_AGENT},
            )
        # EDGAR uses the User-Agent for rate limiting, not auth. Any 200-level response is fine.
        if resp.status_code < 400:
            return ServiceCheck(name="SEC EDGAR (Filings)", status="ok", message=f"User-Agent set: {settings.SEC_EDGAR_USER_AGENT}")
        else:
            return ServiceCheck(name="SEC EDGAR (Filings)", status="ok", message=f"User-Agent set (HTTP {resp.status_code} — EDGAR may be throttling)")
    except Exception as e:
        return ServiceCheck(name="SEC EDGAR (Filings)", status="error", message=str(e))


async def _check_celery() -> ServiceCheck:
    try:
        from app.celery_app import celery_app
        inspector = celery_app.control.inspect(timeout=2)
        ping_result = inspector.ping()
        if ping_result:
            worker_count = len(ping_result)
            return ServiceCheck(
                name="Celery Workers",
                status="ok",
                message=f"{worker_count} worker(s) online",
                details={"workers": list(ping_result.keys())},
            )
        return ServiceCheck(name="Celery Workers", status="error", message="No workers responding")
    except Exception as e:
        return ServiceCheck(name="Celery Workers", status="error", message=str(e))


@router.get("/services", response_model=ServiceStatusResponse)
async def check_all_services():
    """Check connectivity of all external services and infrastructure — all checks run concurrently."""
    import asyncio
    checks = await asyncio.gather(
        _check_api_server(),
        _check_postgres(),
        _check_redis(),
        _check_celery(),
        _check_alpaca(),
        _check_anthropic(),
        _check_finnhub(),
        _check_fred(),
        _check_edgar(),
    )

    error_count = sum(1 for c in checks if c.status == "error")
    not_configured_count = sum(1 for c in checks if c.status == "not_configured")

    if error_count > 0:
        overall = "error"
    elif not_configured_count > 0:
        overall = "degraded"
    else:
        overall = "ok"

    return ServiceStatusResponse(overall=overall, services=checks)
