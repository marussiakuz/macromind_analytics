"""Base connector interface."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

from person_osint.models import ConnectorQuery, ConnectorResult


def make_cache_key(name: str, query_type: str, params: dict) -> str:
    """Generate deterministic cache key using SHA-256."""
    params_str = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
    return f"{name}:{query_type}:{params_hash}"


class BaseConnector(ABC):
    """Base class for all external API connectors.

    Subclasses must implement: fetch(), health_check(), name, rate_limit.
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Connector name (e.g., 'linkedin', 'habr')."""
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
        """Execute query with audit logging."""
        start_time = datetime.now(timezone.utc)
        try:
            result = await self.fetch(query)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return result
        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
