"""Tests configuration."""

import pytest
import asyncio
from typing import AsyncGenerator

import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_connector():
    """Create a mock connector for testing."""
    from osint_agent.connectors.base import BaseConnector
    from osint_agent.models import ConnectorQuery, ConnectorResult

    class MockConnector(BaseConnector):
        @property
        def name(self) -> str:
            return "mock"

        @property
        def rate_limit(self) -> int:
            return 100

        async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
            return ConnectorResult(
                success=True,
                data={"mock": True},
                source="mock",
            )

        async def health_check(self) -> bool:
            return True

    return MockConnector()
