"""Mock connectors for testing without real API access.

These connectors return realistic test data for development and testing.
Replace with real implementations when API access is available.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult


class MockFNSTaxConnector(BaseConnector):
    """Mock connector for FNS Tax (ФНС «Прозрачный бизнес»).

    Returns: tax debts, disqualifications, mass addresses.
    """

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "7701234567": {
            "has_tax_debt": False,
            "debt_amount": 0.0,
            "is_disqualified_director": False,
            "disqualified_persons": [],
            "has_mass_address": False,
            "provides_reporting": True,
        },
        "7799888777": {
            "has_tax_debt": True,
            "debt_amount": 1500000.0,
            "is_disqualified_director": False,
            "disqualified_persons": [],
            "has_mass_address": True,
            "provides_reporting": True,
        },
        "7701234569": {
            "has_tax_debt": False,
            "debt_amount": 0.0,
            "is_disqualified_director": True,
            "disqualified_persons": ["Иванов Иван Иванович"],
            "has_mass_address": False,
            "provides_reporting": False,
        },
    }

    @property
    def name(self) -> str:
        return "fns_tax"

    @property
    def rate_limit(self) -> int:
        return 60

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(success=False, source=self.name, error="INN required")

        await asyncio.sleep(0.05)
        data = self.MOCK_DATA.get(inn)

        if data:
            return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")
        return ConnectorResult(success=False, source=self.name, error="Not found")

    async def health_check(self) -> bool:
        return True


class MockKADConnector(BaseConnector):
    """Mock connector for KAD Arbitr (КАД Арбитр).

    Returns: arbitration court cases.
    """

    MOCK_DATA: dict[str, list[dict[str, Any]]] = {
        "7701234567": [
            {
                "case_number": "А40-123456/2024",
                "court": "Арбитражный суд г. Москвы",
                "case_type": "Исковое заявление",
                "status": "Рассматривается",
                "amount": 500000.0,
                "plaintiff": 'ООО "Кредитор"',
                "defendant": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                "date": "2024-06-15T00:00:00",
            }
        ],
        "7799888777": [
            {
                "case_number": "А40-789012/2023",
                "court": "Арбитражный суд г. Москвы",
                "case_type": "Банкротство",
                "status": "Производство возбуждено",
                "amount": 10000000.0,
                "plaintiff": "ФНС",
                "defendant": 'ООО "МАССОВЫЙ АДРЕС"',
                "date": "2023-12-01T00:00:00",
            },
            {
                "case_number": "А40-345678/2024",
                "court": "Арбитражный суд г. Москвы",
                "case_type": "Исковое заявление",
                "status": "Решение вынесено",
                "amount": 8000000.0,
                "plaintiff": 'ООО "Поставщик"',
                "defendant": 'ООО "МАССОВЫЙ АДРЕС"',
                "date": "2024-03-20T00:00:00",
            },
        ],
    }

    @property
    def name(self) -> str:
        return "kad"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(success=False, source=self.name, error="INN required")

        await asyncio.sleep(0.05)
        cases = self.MOCK_DATA.get(inn, [])
        return ConnectorResult(
            success=True,
            data={"cases": cases, "total": len(cases)},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True


class MockSudrfConnector(BaseConnector):
    """Mock connector for ГАС Правосудие (sudrf.ru).

    Returns: general jurisdiction court cases.
    """

    MOCK_DATA: dict[str, list[dict[str, Any]]] = {
        "7701234567": [],
        "7799888777": [
            {
                "case_number": "2-1234/2024",
                "court": "Тверской районный суд г. Москвы",
                "case_type": "Гражданское",
                "status": "Рассматривается",
                "amount": 2000000.0,
                "plaintiff": "Петров П.П.",
                "defendant": 'ООО "МАССОВЫЙ АДРЕС"',
                "date": "2024-05-10T00:00:00",
            }
        ],
    }

    @property
    def name(self) -> str:
        return "sudrf"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(success=False, source=self.name, error="INN required")

        await asyncio.sleep(0.05)
        cases = self.MOCK_DATA.get(inn, [])
        return ConnectorResult(
            success=True,
            data={"cases": cases, "total": len(cases)},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True


class MockFSSPConnector(BaseConnector):
    """Mock connector for ФССП (fssp.gov.ru).

    Returns: bailiff execution productions.
    """

    MOCK_DATA: dict[str, list[dict[str, Any]]] = {
        "7701234567": [],
        "7799888777": [
            {
                "production_number": "12345/24/7700001-ИП",
                "amount": 1500000.0,
                "status": "Возбуждено",
                "date": "2024-01-15T00:00:00",
            },
            {
                "production_number": "67890/24/7700002-ИП",
                "amount": 500000.0,
                "status": "Окончено",
                "date": "2023-11-20T00:00:00",
            },
        ],
    }

    @property
    def name(self) -> str:
        return "fssp"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(success=False, source=self.name, error="INN required")

        await asyncio.sleep(0.05)
        productions = self.MOCK_DATA.get(inn, [])
        return ConnectorResult(
            success=True,
            data={"productions": productions, "total": len(productions)},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True


class MockSanctionConnector(BaseConnector):
    """Mock connector for sanctions registries.

    Checks: OFAC, EU, UK FCDO, UN, Росфинмониторинг.
    """

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "is_sanctioned": False,
            "matches": [],
            "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
        },
        "Санкционный Петр": {
            "is_sanctioned": True,
            "matches": [
                {
                    "registry": "ofac",
                    "name_matched": "SANKTSIONNYI PETR",
                    "name_original": "Санкционный Петр",
                    "match_score": 0.95,
                }
            ],
            "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
        },
    }

    @property
    def name(self) -> str:
        return "sanctions"

    @property
    def rate_limit(self) -> int:
        return 120

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        full_name = query.params.get("full_name")
        if not full_name:
            return ConnectorResult(success=False, source=self.name, error="Name required")

        await asyncio.sleep(0.05)

        # Fuzzy search in mock data
        for name, data in self.MOCK_DATA.items():
            if self._fuzzy_match(full_name, name):
                return ConnectorResult(
                    success=True,
                    data=data,
                    source=f"{self.name}:mock",
                )

        # Default: not sanctioned
        return ConnectorResult(
            success=True,
            data={
                "is_sanctioned": False,
                "matches": [],
                "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
            },
            source=f"{self.name}:mock",
        )

    def _fuzzy_match(self, name1: str, name2: str) -> bool:
        """Simple fuzzy matching."""
        return name1.lower().strip() == name2.lower().strip()

    async def health_check(self) -> bool:
        return True


class MockNewsConnector(BaseConnector):
    """Mock connector for news search.

    Uses: Tavily, Brave Search, RSS feeds.
    """

    MOCK_DATA: dict[str, list[dict[str, Any]]] = {
        "7701234567": [
            {
                "title": 'ООО "Тестовая компания" привлекла инвестиции',
                "url": "https://example.com/news/1",
                "source": "РБК",
                "date": "2024-06-01T00:00:00",
                "snippet": "Компания привлекла 100 млн руб. в раунде А...",
                "is_negative": False,
            }
        ],
        "7799888777": [
            {
                "title": 'ООО "Массовый адрес" подозревается в мошенничестве',
                "url": "https://example.com/news/2",
                "source": "Коммерсантъ",
                "date": "2024-05-15T00:00:00",
                "snippet": "Возбуждено уголовное дело по факту мошенничества...",
                "is_negative": True,
            },
            {
                "title": 'Претензии к ООО "Массовый адрес" от поставщиков',
                "url": "https://example.com/news/3",
                "source": "Ведомости",
                "date": "2024-04-20T00:00:00",
                "snippet": "Несколько поставщиков заявили о нарушении сроков оплаты...",
                "is_negative": True,
            },
        ],
    }

    @property
    def name(self) -> str:
        return "news"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        company_name = query.params.get("company_name")
        inn = query.params.get("inn")

        await asyncio.sleep(0.1)

        # Search by INN or company name
        articles = []
        if inn:
            articles = self.MOCK_DATA.get(inn, [])
        elif company_name:
            # Simple search by name
            for key, value in self.MOCK_DATA.items():
                articles.extend(value)

        return ConnectorResult(
            success=True,
            data={"articles": articles, "total": len(articles)},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True


class MockTenderConnector(BaseConnector):
    """Mock connector for government tenders (zakupki.gov.ru)."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "7701234567": {
            "tenders": [
                {
                    "tender_id": "0373100002424000001",
                    "status": "Завершена",
                    "amount": 5000000.0,
                    "participants_count": 3,
                    "winner": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
                    "is_single_source": False,
                }
            ],
            "total": 1,
            "single_source_percent": 0.0,
            "same_competitors": False,
            "in_ndr": False,
        },
        "7799888777": {
            "tenders": [
                {
                    "tender_id": "0373100002424000002",
                    "status": "Завершена",
                    "amount": 10000000.0,
                    "participants_count": 1,
                    "winner": 'ООО "МАССОВЫЙ АДРЕС"',
                    "is_single_source": True,
                },
                {
                    "tender_id": "0373100002424000003",
                    "status": "Завершена",
                    "amount": 8000000.0,
                    "participants_count": 1,
                    "winner": 'ООО "МАССОВЫЙ АДРЕС"',
                    "is_single_source": True,
                },
            ],
            "total": 2,
            "single_source_percent": 100.0,
            "same_competitors": False,
            "in_ndr": True,
        },
    }

    @property
    def name(self) -> str:
        return "tenders"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(success=False, source=self.name, error="INN required")

        await asyncio.sleep(0.05)
        data = self.MOCK_DATA.get(inn)

        if data:
            return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

        return ConnectorResult(
            success=True,
            data={"tenders": [], "total": 0, "single_source_percent": 0, "same_competitors": False, "in_ndr": False},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True


class MockPEPConnector(BaseConnector):
    """Mock connector for PEP (Politically Exposed Persons) check."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {"is_pep": False, "source": "pep_database", "details": ""},
        "Политиков Петр Петрович": {
            "is_pep": True,
            "source": "pep_database",
            "details": "Заместитель министра (2018-2022)",
        },
    }

    @property
    def name(self) -> str:
        return "pep"

    @property
    def rate_limit(self) -> int:
        return 60

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        full_name = query.params.get("full_name")
        if not full_name:
            return ConnectorResult(success=False, source=self.name, error="Name required")

        await asyncio.sleep(0.05)

        # Default: not PEP
        data = self.MOCK_DATA.get(full_name, {"is_pep": False, "source": "pep_database", "details": ""})
        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True


class MockSocialConnector(BaseConnector):
    """Mock connector for social network search."""

    MOCK_DATA: dict[str, list[dict[str, Any]]] = {
        "Иванов Иван Иванович": [
            {
                "platform": "vk",
                "url": "https://vk.com/ivanov_ivan",
                "name": "Иван Иванов",
                "city": "Москва",
                "workplace": 'ООО "Тестовая компания"',
                "education": "МГУ",
                "birth_year": 1985,
                "friends_count": 350,
                "is_public": True,
            },
            {
                "platform": "linkedin",
                "url": "https://linkedin.com/in/ivanov-ivan",
                "name": "Ivan Ivanov",
                "city": "Moscow",
                "workplace": "Test Company LLC",
                "education": "Moscow State University",
                "birth_year": 1985,
                "friends_count": None,
                "is_public": True,
            },
        ],
    }

    @property
    def name(self) -> str:
        return "social"

    @property
    def rate_limit(self) -> int:
        return 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        full_name = query.params.get("full_name")
        if not full_name:
            return ConnectorResult(success=False, source=self.name, error="Name required")

        await asyncio.sleep(0.1)
        profiles = self.MOCK_DATA.get(full_name, [])

        return ConnectorResult(
            success=True,
            data={"profiles": profiles, "total": len(profiles)},
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True
