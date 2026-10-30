"""Tests for Habr connector."""

import pytest
from person_osint.connectors.habr import MockHabrConnector
from person_osint.models import ConnectorQuery


@pytest.fixture
def connector():
    return MockHabrConnector()


@pytest.mark.unit
class TestMockHabrConnector:
    """Tests for MockHabrConnector."""

    def test_name(self, connector):
        assert connector.name == "habr"

    @pytest.mark.asyncio
    async def test_fetch_known_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="habr", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["karma"] == 125.5
        assert result.data["company"] == "Яндекс"
        assert len(result.data["articles"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="habr", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_articles(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="habr", params={"full_name": "Иванов Иван Иванович"})
        )
        articles = result.data["articles"]
        assert articles[0]["platform"] == "habr"
        assert "микросервисы" in articles[0]["tags"]
