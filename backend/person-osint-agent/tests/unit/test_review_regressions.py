from datetime import date
from unittest.mock import patch

import httpx
import pytest

from person_osint.candidate_ranker import CandidateRanker
from person_osint.competence_scorer import CompetenceScorer
from person_osint.models import ConnectorResult, Experience, PersonProfile
from person_osint.profile_builder import ProfileBuilder
from person_osint.search import PeopleSearchTool


def test_namesakes_keep_account_identity_and_sort_by_city():
    users = [
        {"user_id": 1, "full_name": "Иван Иванов", "city": "Москва"},
        {"user_id": 2, "full_name": "Иван Иванов", "city": "Казань"},
    ]
    result = ConnectorResult(success=True, data={"found": True, "users": users})
    candidates = CandidateRanker().rank(
        "Иван Иванов",
        query_city="Казань",
        results={"vk": result},
    )
    assert len(candidates) == 2
    assert candidates[0].selected_accounts == {"vk": "2"}
    assert candidates[0].city == "Казань"


def test_empty_search_does_not_invent_candidate():
    assert CandidateRanker().rank("Nobody", results={}) == []


@pytest.mark.asyncio
async def test_default_hub_has_no_mock_checks_or_profiles():
    tool = PeopleSearchTool(demo_mode=False)
    assert tool.hub.get_connector("sanctions") is None
    assert type(tool.hub.get_connector("linkedin")).__name__ == "LinkedInConnector"
    assert type(tool.hub.get_connector("vk")).__name__ == "VKConnector"
    with pytest.raises(ValueError, match="selected_accounts"):
        await tool.get_full_profile("Иван Иванов")


@pytest.mark.asyncio
async def test_selected_vk_account_is_loaded_by_id_through_api(monkeypatch):
    from person_osint.main import app

    tool = PeopleSearchTool(demo_mode=False)
    calls = []

    async def fake_fetch(source, params):
        calls.append((source, params))
        return ConnectorResult(
            success=True,
            source="vk",
            data={
                "found": True,
                "user": {
                    "user_id": 2,
                    "full_name": "Иван Иванов",
                    "city": "Казань",
                    "profile_url": "https://vk.com/id2",
                },
            },
        )

    monkeypatch.setattr(tool.hub, "fetch", fake_fetch)
    monkeypatch.setattr("person_osint.api.get_people_search", lambda: tool)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/people/profile",
            json={
                "full_name": "Иван Иванов",
                "city": "Казань",
                "selected_accounts": {"vk": "2"},
            },
        )
        missing = await client.post("/api/v1/people/profile", json={"full_name": "Иван Иванов"})
    assert response.status_code == 200
    assert missing.status_code == 400
    data = response.json()
    assert data["social_profiles"][0]["url"] == "https://vk.com/id2"
    assert calls == [
        ("vk", {"full_name": "Иван Иванов", "city": "Казань", "action": "get", "user_id": "2"})
    ]
    assert data["is_sanctioned"] is None
    assert data["source_statuses"]["sanctions"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "accounts",
    [
        {"vk": "../users"},
        {"github": "a/b"},
        {"linkedin": "https://example.com/in/a"},
        {"unknown": "1"},
    ],
)
async def test_invalid_accounts_are_rejected(accounts):
    with pytest.raises(ValueError, match="Некорректный"):
        await PeopleSearchTool(demo_mode=False).get_full_profile("Test", selected_accounts=accounts)


@pytest.mark.asyncio
async def test_demo_profiles_preserve_test_provenance():
    profile = await PeopleSearchTool(demo_mode=True).get_full_profile("Иванов Иван Иванович")
    assert profile.is_demo
    assert profile.source_statuses["sanctions"] == "demo"
    assert profile.source_details["linkedin"] == "linkedin:mock"


def test_unavailable_and_skipped_checks_stay_unknown():
    profile = ProfileBuilder().build_from_results(
        "Test",
        {
            "sanctions": ConnectorResult(
                success=True, source="sanctions:skipped", data={"skipped": True}
            ),
            "pep": ConnectorResult(success=False, source="pep:unavailable"),
        },
    )
    assert profile.is_sanctioned is None
    assert profile.is_pep is None
    assert profile.source_statuses == {"sanctions": "not_checked", "pep": "unavailable"}


def test_ongoing_experience_uses_current_month():
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 18)

    profile = PersonProfile(
        experience=[Experience(company="A", position="Engineer", start_date="2025-04")]
    )
    with patch("person_osint.competence_scorer.date", FixedDate):
        assert CompetenceScorer()._score_experience(profile) == 22.5
