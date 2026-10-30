"""Tests for GitHub connector."""

import pytest
from person_osint.connectors.github import MockGitHubConnector
from person_osint.models import ConnectorQuery


@pytest.fixture
def connector():
    return MockGitHubConnector()


@pytest.mark.unit
class TestMockGitHubConnector:
    """Tests for MockGitHubConnector."""

    def test_name(self, connector):
        assert connector.name == "github"

    @pytest.mark.asyncio
    async def test_fetch_known_user(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="github", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["username"] == "ivanov-dev"
        assert result.data["company"] == "Yandex"
        assert result.data["public_repos"] == 42
        assert result.data["followers"] == 350

    @pytest.mark.asyncio
    async def test_fetch_unknown_user(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="github", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_repos(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="github", params={"full_name": "Иванов Иван Иванович"})
        )
        repos = result.data["repos"]
        assert len(repos) == 3
        assert repos[0]["name"] == "ml-pipeline"
        assert repos[0]["stars"] == 342
        assert repos[0]["language"] == "Python"

    @pytest.mark.asyncio
    async def test_fetch_notable_repos(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="github", params={"full_name": "Иванов Иван Иванович"})
        )
        notable = result.data["notable_repos"]
        assert len(notable) == 2
        assert all(r["stars"] > 10 for r in notable)

    @pytest.mark.asyncio
    async def test_fetch_top_languages(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="github", params={"full_name": "Иванов Иван Иванович"})
        )
        languages = result.data["top_languages"]
        assert "Python" in languages
        assert languages[0] == "Python"
