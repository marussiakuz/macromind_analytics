"""Redis cache for connector results."""

import json
from datetime import datetime
from typing import Any

import redis.asyncio as redis

from osint_agent.config import settings


class CacheEntry:
    """Cache entry with TTL."""

    def __init__(self, data: Any, ttl_seconds: int):
        self.data = data
        self.ttl_seconds = ttl_seconds
        self.created_at = datetime.utcnow()


class RedisCache:
    """Redis cache for connector results."""

    # TTL by data type (seconds)
    TTL = {
        "company_legal": 86400,    # 24 hours
        "court_cases": 43200,      # 12 hours
        "sanctions": 21600,        # 6 hours
        "news": 3600,              # 1 hour
        "bailiff": 43200,          # 12 hours
        "tenders": 43200,          # 12 hours
        "social": 3600,            # 1 hour
        "whois": 86400,            # 24 hours
        "financial": 86400,        # 24 hours
        "pep": 86400,              # 24 hours
    }

    def __init__(self):
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        if not self._client:
            return None

        try:
            value = await self._client.get(f"osint:{key}")
            if value:
                return json.loads(value)
        except Exception:
            pass
        return None

    async def set(
        self,
        key: str,
        value: Any,
        data_type: str = "company_legal",
    ) -> None:
        """Set value in cache with TTL."""
        if not self._client:
            return

        ttl = self.TTL.get(data_type, 3600)
        try:
            await self._client.setex(
                f"osint:{key}",
                ttl,
                json.dumps(value, default=str),
            )
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        if not self._client:
            return

        try:
            await self._client.delete(f"osint:{key}")
        except Exception:
            pass

    async def clear(self, pattern: str = "*") -> None:
        """Clear cache entries matching pattern."""
        if not self._client:
            return

        try:
            async for key in self._client.scan_iter(f"osint:{pattern}"):
                await self._client.delete(key)
        except Exception:
            pass


# Global instance
cache = RedisCache()
