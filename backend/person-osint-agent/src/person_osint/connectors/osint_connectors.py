"""Sanctions Connector — проверка по санкционным реестрам.

OSINT E.6: OFAC SDN, EU Consolidated, UK FCDO, UN, Росфинмониторинг.
"""

from typing import Any

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class MockSanctionsConnector(BaseConnector):
    """Mock sanctions connector."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "is_sanctioned": False,
            "matches": [],
            "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
            "source": "sanctions",
        },
        "Санкционный Петр Петрович": {
            "found": True,
            "is_sanctioned": True,
            "matches": [
                {
                    "registry": "ofac",
                    "name_matched": "SANKTSIONNYI PETR",
                    "name_original": "Санкционный Петр Петрович",
                    "match_score": 0.95,
                }
            ],
            "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
            "source": "sanctions",
        },
    }

    @property
    def name(self) -> str:
        return "sanctions"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name", "")
        data = self.MOCK_DATA.get(full_name, {
            "found": True,
            "is_sanctioned": False,
            "matches": [],
            "registries_checked": ["ofac", "eu", "uk", "un", "rosfin"],
            "source": "sanctions",
        })

        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True


class MockCourtsConnector(BaseConnector):
    """Mock courts connector (kad.arbitr.ru, sudrf.ru)."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "has_cases": False,
            "arbitration_cases": [],
            "general_cases": [],
            "source": "courts",
        },
        "Судебный Петр Петрович": {
            "found": True,
            "has_cases": True,
            "arbitration_cases": [
                {
                    "case_number": "А40-123456/2024",
                    "court": "Арбитражный суд г. Москвы",
                    "type": "Исковое заявление",
                    "status": "Рассматривается",
                    "amount": 5000000.0,
                    "date": "2024-06-15",
                }
            ],
            "general_cases": [],
            "source": "courts",
        },
    }

    @property
    def name(self) -> str:
        return "courts"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name", "")
        data = self.MOCK_DATA.get(full_name, {
            "found": True,
            "has_cases": False,
            "arbitration_cases": [],
            "general_cases": [],
            "source": "courts",
        })

        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True


class MockFSSPConnector(BaseConnector):
    """Mock FSSP connector (fssp.gov.ru)."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "has_productions": False,
            "productions": [],
            "total_debt": 0,
            "source": "fssp",
        },
        "Должник Петр Петрович": {
            "found": True,
            "has_productions": True,
            "productions": [
                {
                    "number": "12345/24/7700001-ИП",
                    "amount": 1500000.0,
                    "status": "Возбуждено",
                    "date": "2024-01-15",
                }
            ],
            "total_debt": 1500000.0,
            "source": "fssp",
        },
    }

    @property
    def name(self) -> str:
        return "fssp"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name", "")
        data = self.MOCK_DATA.get(full_name, {
            "found": True,
            "has_productions": False,
            "productions": [],
            "total_debt": 0,
            "source": "fssp",
        })

        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True


class MockPEPConnector(BaseConnector):
    """Mock PEP connector (номер.орг)."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "is_pep": False,
            "source": "pep",
        },
        "Политиков Петр Петрович": {
            "found": True,
            "is_pep": True,
            "details": "Заместитель министра (2018-2022)",
            "source": "pep",
        },
    }

    @property
    def name(self) -> str:
        return "pep"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name", "")
        data = self.MOCK_DATA.get(full_name, {
            "found": True,
            "is_pep": False,
            "source": "pep",
        })

        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True


class MockNewsConnector(BaseConnector):
    """Mock news search connector."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "Иванов Иван Иванович": {
            "found": True,
            "has_negative": False,
            "articles": [
                {
                    "title": "Иванов получил награду за инновации",
                    "url": "https://example.com/news/1",
                    "source": "РБК",
                    "date": "2024-06-01",
                    "snippet": "Иванов Иван Иванович получил премию...",
                    "is_negative": False,
                }
            ],
            "source": "news",
        },
        "Скандалов Петр Петрович": {
            "found": True,
            "has_negative": True,
            "articles": [
                {
                    "title": "Скандалов подозревается в мошенничестве",
                    "url": "https://example.com/news/2",
                    "source": "Коммерсантъ",
                    "date": "2024-05-15",
                    "snippet": "Возбуждено уголовное дело...",
                    "is_negative": True,
                }
            ],
            "source": "news",
        },
    }

    @property
    def name(self) -> str:
        return "news"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        import asyncio
        await asyncio.sleep(0.05)

        full_name = query.params.get("full_name", "")
        data = self.MOCK_DATA.get(full_name, {
            "found": True,
            "has_negative": False,
            "articles": [],
            "source": "news",
        })

        return ConnectorResult(success=True, data=data, source=f"{self.name}:mock")

    async def health_check(self) -> bool:
        return True
