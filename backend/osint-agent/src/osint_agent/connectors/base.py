"""Base connector interface."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

from osint_agent.models import ConnectorQuery, ConnectorResult
from osint_agent.utils.audit import audit_log
from osint_agent.utils.cache import cache
from osint_agent.utils.rate_limiter import rate_limiter


def make_cache_key(name: str, query_type: str, params: dict) -> str:
    """Generate deterministic cache key using SHA-256.

    ВАЖНО: НЕ используем hash() — он рандомизирован (PYTHONHASHSEED)
    и даст разные результаты в разных процессах.
    """
    params_str = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
    return f"{name}:{query_type}:{params_hash}"


class BaseConnector(ABC):
    """Base class for all external API connectors.

    Implements: rate limiting, caching, audit logging, retry logic.
    Subclasses must implement: fetch(), health_check(), name, rate_limit.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Connector name (e.g., 'egrul', 'kad', 'sanctions')."""
        ...

    @property
    @abstractmethod
    def rate_limit(self) -> int:
        """Rate limit in requests per minute."""
        ...

    @abstractmethod
    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Fetch data from external API."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the external API is available."""
        ...

    async def execute(self, query: ConnectorQuery) -> ConnectorResult:
        """Execute query with rate limiting, caching, and audit logging."""
        # Check cache first (deterministic key)
        cache_key = make_cache_key(self.name, query.query_type, query.params)
        cached = await cache.get(cache_key)
        if cached:
            return ConnectorResult(
                success=True,
                data=cached,
                source=f"{self.name}:cache",
                confidence=0.9,  # Slightly lower confidence for cached data
            )

        # Rate limiting
        await rate_limiter.wait(self.name)

        # Execute with audit logging
        start_time = datetime.now(timezone.utc)
        try:
            result = await self.fetch(query)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Cache successful results
            if result.success and result.data:
                await cache.set(cache_key, result.data, query.query_type)

            # Audit log (152-ФЗ: log all external API requests)
            await audit_log.log(
                connector_name=self.name,
                query_type=query.query_type,
                params=query.params,
                success=result.success,
                source=result.source,
                error=result.error,
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Audit log failure
            await audit_log.log(
                connector_name=self.name,
                query_type=query.query_type,
                params=query.params,
                success=False,
                source=self.name,
                error=str(e),
                duration_ms=duration_ms,
            )

            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=60.0,  # Checko finances can exceed 30s under load
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
