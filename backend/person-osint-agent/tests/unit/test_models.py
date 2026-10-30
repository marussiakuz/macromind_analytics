"""Tests for Pydantic models."""

import pytest
from person_osint.models import (
    PersonProfile, Skill, Experience, Education,
    GitHubProfile, Publication, Article, Book,
    SocialProfile, PersonConnection, RedFlag,
    CandidateMatch, CompetenceAssessment,
    ConnectorQuery, ConnectorResult,
)


@pytest.mark.unit
class TestPersonProfile:
    """Tests for PersonProfile model."""

    def test_creation(self):
        profile = PersonProfile(
            full_name="Иванов Иван Иванович",
            current_position="CTO",
            current_company="Яндекс",
        )
        assert profile.full_name == "Иванов Иван Иванович"
        assert profile.current_position == "CTO"
        assert profile.current_company == "Яндекс"
        assert profile.id is not None

    def test_default_values(self):
        profile = PersonProfile()
        assert profile.full_name is None
        assert profile.skills == []
        assert profile.experience == []
        assert profile.is_sanctioned is None
        assert profile.competence_score is None

    def test_with_skills(self):
        profile = PersonProfile(
            full_name="Test",
            skills=[
                Skill(name="Python", level="expert", evidence=["linkedin"]),
                Skill(name="ML", level="senior", evidence=["habr"]),
            ],
        )
        assert len(profile.skills) == 2
        assert profile.skills[0].name == "Python"

    def test_with_experience(self):
        profile = PersonProfile(
            full_name="Test",
            experience=[
                Experience(company="Яндекс", position="CTO", start_date="2020-01"),
                Experience(company="Google", position="SWE", start_date="2015-03", end_date="2019-12"),
            ],
        )
        assert len(profile.experience) == 2
        assert profile.experience[0].company == "Яндекс"

    def test_with_red_flags(self):
        profile = PersonProfile(
            full_name="Test",
            red_flags=[
                RedFlag(priority="HIGH", category="sanctions", description="Found in OFAC"),
            ],
        )
        assert len(profile.red_flags) == 1
        assert profile.red_flags[0].priority == "HIGH"

    def test_serialization(self):
        profile = PersonProfile(
            full_name="Test",
            skills=[Skill(name="Python")],
        )
        data = profile.model_dump()
        assert "full_name" in data
        assert "skills" in data
        assert data["full_name"] == "Test"


@pytest.mark.unit
class TestSkill:
    """Tests for Skill model."""

    def test_creation(self):
        skill = Skill(name="Python", level="expert")
        assert skill.name == "Python"
        assert skill.level == "expert"
        assert skill.evidence == []

    def test_with_evidence(self):
        skill = Skill(
            name="Python",
            evidence=["linkedin_endorsement", "github_repos"],
        )
        assert len(skill.evidence) == 2


@pytest.mark.unit
class TestExperience:
    """Tests for Experience model."""

    def test_creation(self):
        exp = Experience(company="Яндекс", position="CTO")
        assert exp.company == "Яндекс"
        assert exp.position == "CTO"
        assert exp.start_date is None

    def test_with_dates(self):
        exp = Experience(
            company="Google",
            position="SWE",
            start_date="2015-03",
            end_date="2019-12",
            description="Search algorithms",
            source="linkedin",
        )
        assert exp.start_date == "2015-03"
        assert exp.end_date == "2019-12"


@pytest.mark.unit
class TestCandidateMatch:
    """Tests for CandidateMatch model."""

    def test_creation(self):
        candidate = CandidateMatch(
            full_name="Иванов Иван",
            match_score=85.0,
            matched_fields=["name", "company"],
            current_company="Яндекс",
            found_sources=["linkedin", "habr"],
        )
        assert candidate.match_score == 85.0
        assert "company" in candidate.matched_fields


@pytest.mark.unit
class TestConnectorModels:
    """Tests for ConnectorQuery and ConnectorResult."""

    def test_query_creation(self):
        query = ConnectorQuery(
            query_type="linkedin",
            params={"full_name": "Иванов"},
        )
        assert query.query_type == "linkedin"
        assert query.params["full_name"] == "Иванов"

    def test_result_success(self):
        result = ConnectorResult(
            success=True,
            data={"found": True},
            source="linkedin",
        )
        assert result.success is True
        assert result.data["found"] is True

    def test_result_failure(self):
        result = ConnectorResult(
            success=False,
            source="linkedin",
            error="API key not configured",
        )
        assert result.success is False
        assert result.error == "API key not configured"
