from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Application ──
    APP_NAME: str = "ai-trader"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me-in-production"
    TRADING_MODE: str = "paper"

    # ── PostgreSQL ──
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "trader"
    POSTGRES_USER: str = "trader"
    POSTGRES_PASSWORD: str = "trader"
    DATABASE_URL: str = ""

    # ── Redis ──
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = ""

    # ── Alpaca ──
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"

    # ── Anthropic (Claude) ──
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL_FAST: str = "claude-3-5-haiku-20241022"
    CLAUDE_MODEL_SMART: str = "claude-sonnet-4-20250514"

    # ── Finnhub ──
    FINNHUB_API_KEY: str = ""

    # ── FRED ──
    FRED_API_KEY: str = ""

    # ── SEC EDGAR ──
    SEC_EDGAR_USER_AGENT: str = ""

    # ── Risk Management ──
    RISK_MAX_TRADE_DOLLARS: float = 1000.0
    RISK_MAX_POSITION_PCT: float = 10.0
    RISK_MAX_SECTOR_PCT: float = 25.0
    RISK_DAILY_LOSS_LIMIT: float = 500.0
    RISK_MAX_DRAWDOWN_PCT: float = 15.0
    RISK_MIN_CONFIDENCE: float = 0.6

    # ── Signal Weights ──
    SIGNAL_WEIGHT_ML: float = 0.3
    SIGNAL_WEIGHT_CLAUDE: float = 0.4
    SIGNAL_WEIGHT_ANALYST: float = 0.3

    # ── Trading Parameters ──
    POSITION_SIZE_METHOD: str = "fixed_fractional"
    POSITION_SIZE_RISK_PCT: float = 2.0
    DEFAULT_STOP_LOSS_PCT: float = 5.0
    DEFAULT_TAKE_PROFIT_PCT: float = 10.0
    AUTO_EXECUTE: bool = False

    # ── Autonomous Mode ──
    # When enabled, the system fully manages the account: auto-approves trades,
    # sizes positions as a % of actual portfolio value, and reinvests profits.
    AUTONOMOUS_MODE: bool = False
    AUTONOMOUS_POSITION_PCT: float = 10.0  # Max % of portfolio per trade in autonomous mode

    # ── Scheduled Task Intervals (seconds) ──
    COLLECT_PRICES_INTERVAL_SEC: int = 60
    COLLECT_NEWS_INTERVAL_SEC: int = 1800
    COLLECT_ECONOMIC_INTERVAL_SEC: int = 86400
    COLLECT_FILINGS_INTERVAL_SEC: int = 21600
    ANALYZE_NEWS_INTERVAL_SEC: int = 900
    ANALYZE_FILINGS_INTERVAL_SEC: int = 3600
    CONTEXT_SYNTHESIS_INTERVAL_SEC: int = 7200
    DECISION_CYCLE_INTERVAL_SEC: int = 1800
    ML_SIGNAL_INTERVAL_SEC: int = 3600
    PORTFOLIO_SYNC_INTERVAL_SEC: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_sync_database_url(self) -> str:
        """Sync URL for Alembic migrations."""
        if self.DATABASE_URL:
            return self.DATABASE_URL.replace("+asyncpg", "")
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"


settings = Settings()
