"""Rate limiter for external API requests."""

import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter per connector."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"tokens": 0, "last_update": 0}
        )
        self._lock = asyncio.Lock()

    async def wait(self, connector_name: str, tokens: int = 1) -> None:
        """Wait until tokens are available for the connector."""
        if not self._enabled:
            return

        async with self._lock:
            bucket = self._buckets[connector_name]
            now = time.monotonic()

            # Get rate limit for connector
            rate_limit = self._get_rate_limit(connector_name)

            # Refill tokens
            elapsed = now - bucket["last_update"]
            bucket["tokens"] = min(
                rate_limit,
                bucket["tokens"] + elapsed * (rate_limit / 60.0),
            )
            bucket["last_update"] = now

            # Wait if not enough tokens
            if bucket["tokens"] < tokens:
                wait_time = (tokens - bucket["tokens"]) / (rate_limit / 60.0)
                await asyncio.sleep(wait_time)
                bucket["tokens"] = 0
            else:
                bucket["tokens"] -= tokens

    def _get_rate_limit(self, connector_name: str) -> float:
        """Get rate limit (requests per minute) for connector."""
        # Default rate limits per connector
        limits = {
            "egrul": 60,        # 1 req/sec
            "fns_tax": 30,      # 0.5 req/sec
            "kad": 30,          # 0.5 req/sec
            "sudrf": 30,        # 0.5 req/sec
            "fssp": 30,         # 0.5 req/sec
            "sanctions": 120,   # 2 req/sec (local mirror)
            "spark": 60,        # 1 req/sec
            "news": 30,         # 0.5 req/sec
            "vk": 30,           # 0.5 req/sec
            "linkedin": 10,     # ~0.17 req/sec
            "tenders": 30,      # 0.5 req/sec
            "whois": 60,        # 1 req/sec
        }
        return limits.get(connector_name, 30)


# Global instance
rate_limiter = RateLimiter()
