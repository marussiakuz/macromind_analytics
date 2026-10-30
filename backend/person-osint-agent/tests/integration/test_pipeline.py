"""Integration tests — полный цикл через mock-коннекторы.

Проверяет склейку компонентов:
  Hub → Connector → данные → PersonProfile
"""

import pytest
from person_osint.connectors.hub import DataConnectorHub
from person_osint.connectors.linkedin import MockLinkedInConnector
from person_osint.connectors.habr import MockHabrConnector
from person_osint.connectors.vc import MockVCConnector
from person_osint.models import PersonProfile, Skill, Experience


def _build_hub() -> DataConnectorHub:
    """Hub со всеми mock-коннекторами."""
    hub = DataConnectorHub()
    hub.register(MockLinkedInConnector())
    hub.register(MockHabrConnector())
    hub.register(MockVCConnector())
    return hub


@pytest.fixture
def hub():
    return _build_hub()


@pytest.mark.integration
class TestFullPipeline:
    """Полный цикл: запрос → Hub → Connector → PersonProfile."""

    @pytest.mark.asyncio
    async def test_linkedin_to_profile(self, hub):
        """LinkedIn данные → PersonProfile."""
        result = await hub.fetch("linkedin", {"full_name": "Иванов Иван Иванович"})
        assert result.success
        data = result.data

        profile = PersonProfile(
            full_name=data["full_name"],
            current_position=data["current_position"],
            current_company=data["current_company"],
            experience=[
                Experience(company=e["company"], position=e["position"], source="linkedin")
                for e in data["experience"]
            ],
            skills=[
                Skill(name=s["name"], level=s.get("level"), evidence=s.get("evidence", []))
                for s in data["skills"]
            ],
            sources=["linkedin"],
        )

        assert profile.full_name == "Иванов Иван Иванович"
        assert profile.current_company == "Яндекс"
        assert len(profile.experience) == 2
        assert len(profile.skills) == 4
        assert "linkedin" in profile.sources

    @pytest.mark.asyncio
    async def test_multi_source_aggregation(self, hub):
        """Агрегация данных из нескольких источников."""
        linkedin = await hub.fetch("linkedin", {"full_name": "Иванов Иван Иванович"})
        habr = await hub.fetch("habr", {"full_name": "Иванов Иван Иванович"})
        vc = await hub.fetch("vc", {"full_name": "Иванов Иван Иванович"})

        assert linkedin.success
        assert habr.success
        assert vc.success

        # Все три источника нашли человека
        assert linkedin.data["found"] is True
        assert habr.data["found"] is True
        assert vc.data["found"] is True

        # Данные из разных источников
        assert linkedin.data["current_company"] == "Яндекс"
        assert habr.data["company"] == "Яндекс"
        assert vc.data["company"] == "Яндекс"

    @pytest.mark.asyncio
    async def test_partial_results(self, hub):
        """Частичные результаты — не все источники нашли."""
        linkedin = await hub.fetch("linkedin", {"full_name": "Петров Петр Петрович"})
        habr = await hub.fetch("habr", {"full_name": "Петров Петр Петрович"})

        assert linkedin.success
        assert linkedin.data["found"] is True  # Есть в mock LinkedIn

        assert habr.success
        assert habr.data["found"] is False  # Нет в mock Habr

    @pytest.mark.asyncio
    async def test_no_results(self, hub):
        """Нет результатов ни в одном источнике."""
        linkedin = await hub.fetch("linkedin", {"full_name": "Несуществующий Человек"})
        habr = await hub.fetch("habr", {"full_name": "Несуществующий Человек"})
        vc = await hub.fetch("vc", {"full_name": "Несуществующий Человек"})

        assert linkedin.data["found"] is False
        assert habr.data["found"] is False
        assert vc.data["found"] is False

    @pytest.mark.asyncio
    async def test_health_check(self, hub):
        """Health check всех коннекторов."""
        health = await hub.health_check()
        assert len(health) == 3
        assert all(health.values())
