"""Abstract base collector with retry logic, rate limiting, and logging."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx


class BaseCollector(ABC):
    """Base class for all data collectors.

    Provides:
      - httpx async client with configurable timeout
      - Exponential backoff retry
      - Token-bucket rate limiter
      - Per-collector logging
    """

    name: str = "base"
    max_retries: int = 3
    base_delay: float = 1.0  # seconds — first retry delay
    max_requests_per_minute: int = 60

    def __init__(self):
        self.logger = logging.getLogger(f"collector.{self.name}")
        self._request_times: list[float] = []

    # ── HTTP client (created per-run so connections don't leak) ────────────

    def _build_client(self, **kwargs) -> httpx.AsyncClient:
        defaults = {"timeout": httpx.Timeout(30.0), "follow_redirects": True}
        defaults.update(kwargs)
        return httpx.AsyncClient(**defaults)

    # ── Rate limiter ──────────────────────────────────────────────────────

    async def _wait_for_rate_limit(self):
        """Simple sliding-window rate limiter."""
        now = time.monotonic()
        window = 60.0  # 1 minute window
        self._request_times = [t for t in self._request_times if now - t < window]
        if len(self._request_times) >= self.max_requests_per_minute:
            sleep_time = window - (now - self._request_times[0]) + 0.1
            self.logger.debug("Rate limit reached, sleeping %.1fs", sleep_time)
            await asyncio.sleep(sleep_time)
        self._request_times.append(time.monotonic())

    # ── Retry wrapper ─────────────────────────────────────────────────────

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Make an HTTP request with exponential backoff retry."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            await self._wait_for_rate_limit()
            try:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                last_exc = e
                status = e.response.status_code
                # Don't retry client errors (except 429)
                if 400 <= status < 500 and status != 429:
                    self.logger.error(
                        "%s request failed (HTTP %d): %s", self.name, status, url
                    )
                    raise
                delay = self.base_delay * (2 ** attempt)
                self.logger.warning(
                    "%s HTTP %d, retrying in %.1fs (attempt %d/%d): %s",
                    self.name, status, delay, attempt + 1, self.max_retries, url,
                )
                await asyncio.sleep(delay)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                delay = self.base_delay * (2 ** attempt)
                self.logger.warning(
                    "%s connection error, retrying in %.1fs (attempt %d/%d): %s",
                    self.name, delay, attempt + 1, self.max_retries, e,
                )
                await asyncio.sleep(delay)

        self.logger.error("%s all %d retries exhausted for %s", self.name, self.max_retries, url)
        raise last_exc  # type: ignore[misc]

    # ── Abstract interface ────────────────────────────────────────────────

    @abstractmethod
    async def collect(self, **kwargs) -> dict[str, Any]:
        """Run the collection cycle. Returns a summary dict."""
        ...

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)
