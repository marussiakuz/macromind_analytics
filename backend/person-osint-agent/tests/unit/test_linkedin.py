"""Tests for LinkedIn connector."""

import pytest
from person_osint.connectors.linkedin import MockLinkedInConnector
from person_osint.models import ConnectorQuery, ConnectorResult


@pytest.fixture
def connector():
    return MockLinkedInConnector()


@pytest.mark.unit
class TestMockLinkedInConnector:
    """Tests for MockLinkedInConnector."""

    def test_name(self, connector):
        assert connector.name == "linkedin"

    @pytest.mark.asyncio
    async def test_fetch_known_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="linkedin", params={"full_name": "Иванов Иван Иванович"})
        )
        assert result.success
        assert result.data["found"] is True
        assert result.data["current_company"] == "Яндекс"
        assert result.data["current_position"] == "CTO"
        assert len(result.data["experience"]) == 2
        assert len(result.data["education"]) == 1
        assert len(result.data["skills"]) == 4

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="linkedin", params={"full_name": "Неизвестный"})
        )
        assert result.success
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_experience_data(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="linkedin", params={"full_name": "Иванов Иван Иванович"})
        )
        exp = result.data["experience"][0]
        assert exp["company"] == "Яндекс"
        assert exp["position"] == "CTO"
        assert exp["source"] == "linkedin"

    @pytest.mark.asyncio
    async def test_fetch_skills_data(self, connector):
        result = await connector.fetch(
            ConnectorQuery(query_type="linkedin", params={"full_name": "Иванов Иван Иванович"})
        )
        skills = result.data["skills"]
        skill_names = [s["name"] for s in skills]
        assert "Python" in skill_names
        assert "Machine Learning" in skill_names
