"""People Search Tool — главный оркестр поиска людей."""

import asyncio
import time
import re
from urllib.parse import urlparse
from typing import Any

from person_osint.connectors.hub import DataConnectorHub
from person_osint.connectors.linkedin import LinkedInConnector, MockLinkedInConnector
from person_osint.connectors.habr import HabrConnector, MockHabrConnector
from person_osint.connectors.vc import VCConnector, MockVCConnector
from person_osint.connectors.github import GitHubConnector, MockGitHubConnector
from person_osint.connectors.google_scholar import GoogleScholarConnector, MockGoogleScholarConnector
from person_osint.connectors.google_books import GoogleBooksConnector, MockGoogleBooksConnector
from person_osint.connectors.medium import MediumConnector, MockMediumConnector
from person_osint.connectors.vk import VKConnector, MockVKConnector
from person_osint.connectors.username_scanner import MockUsernameScanConnector
from person_osint.connectors.osint_connectors import (
    MockSanctionsConnector, MockCourtsConnector,
    MockFSSPConnector, MockPEPConnector, MockNewsConnector,
)
from person_osint.models import (
    PersonProfile, CandidateMatch, ConnectorResult,
)
from person_osint.profile_builder import ProfileBuilder
from person_osint.competence_scorer import CompetenceScorer
from person_osint.candidate_ranker import CandidateRanker


class PeopleSearchTool:
    """Главный оркестр поиска людей."""

    def __init__(self, hub: DataConnectorHub | None = None, *, demo_mode: bool | None = None):
        from person_osint.config import settings

        self.demo_mode = settings.demo_mode if demo_mode is None else demo_mode
        self.hub = hub or self._build_default_hub()
        self.profile_builder = ProfileBuilder()
        self.scorer = CompetenceScorer()
        self.ranker = CandidateRanker()

    def _build_default_hub(self) -> DataConnectorHub:
        """Demo data is available only through an explicit mode."""
        hub = DataConnectorHub()
        pairs = [
            (LinkedInConnector, MockLinkedInConnector),
            (HabrConnector, MockHabrConnector),
            (VCConnector, MockVCConnector),
            (GitHubConnector, MockGitHubConnector),
            (GoogleScholarConnector, MockGoogleScholarConnector),
            (GoogleBooksConnector, MockGoogleBooksConnector),
            (MediumConnector, MockMediumConnector),
            (VKConnector, MockVKConnector),
        ]
        for real, mock in pairs:
            hub.register(mock() if self.demo_mode else real())
        if self.demo_mode:
            for connector in (
                MockUsernameScanConnector, MockSanctionsConnector,
                MockCourtsConnector, MockFSSPConnector, MockPEPConnector, MockNewsConnector,
            ):
                hub.register(connector())
        return hub

    async def search_candidates(
        self,
        full_name: str,
        nicknames: list[str] | None = None,
        company: str | None = None,
        position: str | None = None,
        city: str | None = None,
        skills: list[str] | None = None,
    ) -> list[CandidateMatch]:
        """Поиск кандидатов (этап 1: disambiguation).

        Args:
            full_name: ФИО (обязательно)
            nicknames: Никнеймы
            company: Компания
            position: Должность
            city: Город
            skills: Навыки

        Returns:
            Список кандидатов для выбора
        """
        # Собираем данные из всех источников параллельно
        sources_to_check = ["linkedin", "habr", "vc", "github", "vk"]

        tasks = {}
        for source in sources_to_check:
            params: dict[str, Any] = {"full_name": full_name}
            if company:
                params["company"] = company
            if city:
                params["city"] = city
            # GitHub: если есть никнейм — ищем по нему (точнее чем по имени)
            if source == "github" and nicknames:
                params["username"] = nicknames[0]
            tasks[source] = self.hub.fetch(source, params)

        # Запускаем параллельно
        results_list = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        results: dict[str, ConnectorResult] = {}
        for source, result in zip(tasks.keys(), results_list):
            if isinstance(result, ConnectorResult):
                results[source] = result

        # Ранжируем кандидатов
        candidates = self.ranker.rank(
            query_full_name=full_name,
            query_company=company,
            query_position=position,
            query_city=city,
            query_skills=skills,
            query_nicknames=nicknames,
            results=results,
        )

        return candidates

    async def get_full_profile(
        self,
        full_name: str,
        nicknames: list[str] | None = None,
        company: str | None = None,
        position: str | None = None,
        city: str | None = None,
        skills: list[str] | None = None,
        sources: list[str] | None = None,
        selected_accounts: dict[str, str] | None = None,
    ) -> PersonProfile:
        """Получить полный профиль (этап 2: после выбора кандидата).

        Args:
            full_name: ФИО
            company: Компания
            position: Должность
            city: Город
            skills: Навыки
            sources: Источники для демонстрационного режима
            selected_accounts: Выбранные аккаунты из результатов /search

        Returns:
            PersonProfile с данными и score
        """
        start_time = time.time()
        if not selected_accounts and not self.demo_mode:
            raise ValueError("Выберите аккаунт из результатов поиска: selected_accounts обязателен")
        for source, account in (selected_accounts or {}).items():
            if source == "vk":
                valid = bool(re.fullmatch(r"[1-9][0-9]*", account))
            elif source == "github":
                valid = bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", account))
            elif source == "linkedin":
                url = urlparse(account)
                valid = (url.scheme == "https" and url.hostname in
                         {"linkedin.com", "www.linkedin.com"} and
                         url.path.startswith("/in/") and len(url.path) > 4 and
                         not url.username and not url.password)
            else:
                valid = False
            if not valid:
                raise ValueError(f"Некорректный аккаунт {source}")

        if selected_accounts:
            # Only explicitly selected accounts may contribute personal data.
            sources = list(selected_accounts)
        elif sources is None:
            sources = [
                "linkedin", "habr", "vc", "github",
                "scholar", "books", "medium", "vk",
                "sanctions", "courts", "fssp", "pep", "news",
            ]

        # Собираем данные параллельно
        tasks = {}
        for source in sources:
            params: dict[str, Any] = {"full_name": full_name}
            if company:
                params["company"] = company
            for field, value in (("city", city), ("position", position), ("skills", skills)):
                if value:
                    params[field] = value
            if source == "vk":
                params["action"] = "search"
            if source == "books":
                params = {"author": full_name}
            # GitHub: если есть никнейм — ищем по нему
            if source == "github" and nicknames:
                params["username"] = nicknames[0]
            if selected_accounts:
                account = selected_accounts[source]
                if source == "vk":
                    params.update(action="get", user_id=account)
                elif source == "github":
                    params["username"] = account
                elif source == "linkedin":
                    params["linkedin_url"] = account
            tasks[source] = self.hub.fetch(source, params)

        results_list = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        results: dict[str, ConnectorResult] = {}
        for source, result in zip(tasks.keys(), results_list):
            if isinstance(result, ConnectorResult):
                results[source] = result

        # Record unavailable checks explicitly; absence never means a clean check.
        for source in ("sanctions", "courts", "fssp", "pep", "news"):
            if source not in results:
                results[source] = ConnectorResult(
                    success=False, source=f"{source}:unavailable",
                    error="Проверка не выполнена",
                )

        # Собираем профиль
        profile = self.profile_builder.build_from_results(full_name, results)

        # Считаем score
        assessment = self.scorer.score(profile)
        profile.competence_score = assessment.overall_score
        profile.competence_assessment = assessment

        # Время поиска
        profile.search_duration_ms = (time.time() - start_time) * 1000

        return profile


# Singleton для использования в API
_people_search: PeopleSearchTool | None = None


def get_people_search() -> PeopleSearchTool:
    """Получить singleton PeopleSearchTool."""
    global _people_search
    if _people_search is None:
        _people_search = PeopleSearchTool()
    return _people_search
