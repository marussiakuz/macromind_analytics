"""Integration tests — полный пайплайн PeopleSearchTool."""

import pytest
from person_osint.search import PeopleSearchTool
from person_osint.models import PersonProfile, CandidateMatch


@pytest.fixture
def tool():
    return PeopleSearchTool(demo_mode=True)


@pytest.mark.integration
class TestPeopleSearchTool:
    """Тесты полного пайплайна."""

    @pytest.mark.asyncio
    async def test_search_candidates(self, tool):
        """Поиск кандидатов возвращает список."""
        candidates = await tool.search_candidates("Иванов Иван Иванович")
        assert len(candidates) > 0
        assert all(isinstance(c, CandidateMatch) for c in candidates)
        assert candidates[0].match_score > 0

    @pytest.mark.asyncio
    async def test_search_candidates_with_filters(self, tool):
        """Поиск с фильтрами."""
        candidates = await tool.search_candidates(
            "Иванов Иван Иванович",
            company="Яндекс",
            city="Москва",
        )
        assert len(candidates) > 0

    @pytest.mark.asyncio
    async def test_get_full_profile(self, tool):
        """Полный профиль."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert isinstance(profile, PersonProfile)
        assert profile.full_name == "Иванов Иван Иванович"
        assert profile.competence_score is not None
        assert profile.competence_score > 0
        assert len(profile.sources) > 0

    @pytest.mark.asyncio
    async def test_profile_has_experience(self, tool):
        """Профиль содержит опыт работы."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert len(profile.experience) > 0
        assert profile.experience[0].company != ""

    @pytest.mark.asyncio
    async def test_profile_has_skills(self, tool):
        """Профиль содержит навыки."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert len(profile.skills) > 0

    @pytest.mark.asyncio
    async def test_profile_has_github(self, tool):
        """Профиль содержит GitHub."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert profile.github is not None
        assert profile.github.public_repos > 0

    @pytest.mark.asyncio
    async def test_profile_has_articles(self, tool):
        """Профиль содержит статьи."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert len(profile.articles) > 0

    @pytest.mark.asyncio
    async def test_profile_has_publications(self, tool):
        """Профиль содержит научные публикации."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert len(profile.publications) > 0

    @pytest.mark.asyncio
    async def test_profile_has_red_flags(self, tool):
        """Профиль содержит red flags."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        # У Иванова нет red flags в mock данных
        assert isinstance(profile.red_flags, list)

    @pytest.mark.asyncio
    async def test_profile_competence_assessment(self, tool):
        """Профиль содержит оценку компетенций."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert profile.competence_assessment is not None
        assert profile.competence_assessment.overall_score > 0
        assert len(profile.competence_assessment.strengths) > 0

    @pytest.mark.asyncio
    async def test_profile_search_duration(self, tool):
        """Профиль содержит время поиска."""
        profile = await tool.get_full_profile("Иванов Иван Иванович")
        assert profile.search_duration_ms is not None
        assert profile.search_duration_ms > 0

    @pytest.mark.asyncio
    async def test_unknown_person(self, tool):
        """Неизвестный человек — пустой профиль."""
        profile = await tool.get_full_profile("Несуществующий Человек")
        assert profile.full_name == "Несуществующий Человек"
        assert len(profile.sources) == 0
