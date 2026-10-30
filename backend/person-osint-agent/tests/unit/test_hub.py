"""Tests for DataConnectorHub."""

import pytest
from person_osint.connectors.hub import DataConnectorHub
from person_osint.connectors.linkedin import MockLinkedInConnector
from person_osint.connectors.habr import MockHabrConnector
from person_osint.connectors.vc import MockVCConnector
from person_osint.models import ConnectorQuery, ConnectorResult


@pytest.fixture
def hub():
    """Hub with mock connectors."""
    h = DataConnectorHub()
    h.register(MockLinkedInConnector())
    h.register(MockHabrConnector())
    h.register(MockVCConnector())
    return h


@pytest.mark.unit
class TestDataConnectorHub:
    """Tests for DataConnectorHub."""

    def test_register_connector(self, hub):
        assert hub.get_connector("linkedin") is not None
        assert hub.get_connector("habr") is not None
        assert hub.get_connector("vc") is not None

    def test_get_nonexistent_connector(self, hub):
        assert hub.get_connector("nonexistent") is None

    @pytest.mark.asyncio
    async def test_fetch_linkedin(self, hub):
        result = await hub.fetch("linkedin", {"full_name": "Иванов Иван Иванович"})
        assert result.success
        assert result.data["found"] is True
        assert result.data["current_company"] == "Яндекс"

    @pytest.mark.asyncio
    async def test_fetch_habr(self, hub):
        result = await hub.fetch("habr", {"full_name": "Иванов Иван Иванович"})
        assert result.success
        assert result.data["found"] is True
        assert result.data["karma"] == 125.5

    @pytest.mark.asyncio
    async def test_fetch_vc(self, hub):
        result = await hub.fetch("vc", {"full_name": "Иванов Иван Иванович"})
        assert result.success
        assert result.data["found"] is True

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, hub):
        result = await hub.fetch("linkedin", {"full_name": "Неизвестный Человек"})
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_unknown_connector(self, hub):
        result = await hub.fetch("nonexistent", {})
        assert not result.success
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_check(self, hub):
        health = await hub.health_check()
        assert len(health) == 3
        assert all(health.values())
