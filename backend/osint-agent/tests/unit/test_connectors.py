"""Unit tests for DataConnectorHub."""

import pytest
from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult


class MockConnector(BaseConnector):
    """Mock connector for testing."""

    def __init__(self, name: str, success: bool = True):
        self._name = name
        self._success = success

    @property
    def name(self) -> str:
        return self._name

    @property
    def rate_limit(self) -> int:
        return 100

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        if self._success:
            return ConnectorResult(
                success=True,
                data={"test": True},
                source=self._name,
            )
        return ConnectorResult(
            success=False,
            source=self._name,
            error="Mock error",
        )

    async def health_check(self) -> bool:
        return True


@pytest.mark.unit
class TestDataConnectorHub:
    """Tests for DataConnectorHub."""

    def test_register_connector(self):
        hub = DataConnectorHub()
        connector = MockConnector("test")
        hub.register(connector)
        assert hub.get_connector("test") is connector

    def test_get_nonexistent_connector(self):
        hub = DataConnectorHub()
        assert hub.get_connector("nonexistent") is None

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        hub = DataConnectorHub()
        connector = MockConnector("egrul")
        hub.register(connector)

        result = await hub.fetch(
            query_type="company_legal",
            params={"inn": "7701234567"},
        )

        assert result.success is True
        assert result.data == {"test": True}

    @pytest.mark.asyncio
    async def test_fetch_fallback(self):
        hub = DataConnectorHub()
        failed_connector = MockConnector("egrul", success=False)
        success_connector = MockConnector("spark")
        hub.register(failed_connector)
        hub.register(success_connector)

        result = await hub.fetch(
            query_type="company_legal",
            params={"inn": "7701234567"},
        )

        assert result.success is True
        assert result.source == "spark"

    @pytest.mark.asyncio
    async def test_fetch_all_failed(self):
        hub = DataConnectorHub()
        failed_connector = MockConnector("egrul", success=False)
        hub.register(failed_connector)

        result = await hub.fetch(
            query_type="company_legal",
            params={"inn": "7701234567"},
        )

        assert result.success is False
        assert "All connectors failed" in result.error

    @pytest.mark.asyncio
    async def test_health_check(self):
        hub = DataConnectorHub()
        connector = MockConnector("test")
        hub.register(connector)

        health = await hub.health_check()
        assert health == {"test": True}
