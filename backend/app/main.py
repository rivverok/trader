import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine, async_session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI Trading Platform starting up (mode=%s)", settings.TRADING_MODE)
    yield
    await engine.dispose()
    logger.info("AI Trading Platform shut down.")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.7.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://riv-ubuntu",
        "https://riv-ubuntu",
        "http://riv-ubuntu:5000",
        "http://localhost:5000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register API routers ─────────────────────────────────────────────
from app.api import router as stocks_router
from app.api.economic import router as economic_router
from app.api.collection import router as collection_router
from app.api.analysis import router as analysis_router
from app.api.ml import router as ml_router
from app.api.analyst import router as analyst_router
from app.api.trades import router as trades_router
from app.api.risk import router as risk_router
from app.api.portfolio import router as portfolio_router
from app.api.system import router as system_router
from app.api.analytics import router as analytics_router
from app.api.alerts import router as alerts_router
from app.api.discovery import router as discovery_router
from app.api.status import router as status_router
from app.api.tasks import router as tasks_router

app.include_router(stocks_router)
app.include_router(economic_router)
app.include_router(collection_router)
app.include_router(analysis_router)
app.include_router(ml_router)
app.include_router(analyst_router)
app.include_router(trades_router)
app.include_router(risk_router)
app.include_router(portfolio_router)
app.include_router(system_router)
app.include_router(analytics_router)
app.include_router(alerts_router)
app.include_router(discovery_router)
app.include_router(status_router)
app.include_router(tasks_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint — verifies database and Redis connectivity."""
    db_ok = False
    redis_ok = False

    # Check PostgreSQL
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT 1"))
            db_ok = result.scalar() == 1
    except Exception as e:
        logger.error("Database health check failed: %s", e)

    # Check Redis
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.get_redis_url(), socket_connect_timeout=2)
        redis_ok = r.ping()
        r.close()
    except Exception as e:
        logger.error("Redis health check failed: %s", e)

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "trading_mode": settings.TRADING_MODE,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
