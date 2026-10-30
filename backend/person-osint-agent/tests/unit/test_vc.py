"""Tests for VC connector."""

import pytest
from person_osint.connectors.vc import MockVCConnector
from person_osint.models import ConnectorQuery


@pytest.fixture
def connector():
    return MockVCConnector()


@pytest.mark.unit
class TestMockVCConnector:
    """Tests for MockVCConnector."""

    def test_name(self, connector):
        assert connector.name == "vc"

    @pytest.mark.asyncio
    async def test_fetch_known_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="vc", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["company"] == "Яндекс"
        assert len(result.data["articles"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="vc", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_articles(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="vc", params={"full_name": "Иванов Иван Иванович"})
        )
        articles = result.data["articles"]
        assert articles[0]["platform"] == "vc"
