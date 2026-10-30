"""Checko API Connector — проверка контрагентов по ИНН/ОГРН.

Источник: https://checko.ru/integration/api

14 методов:
- /company        — ЕГРЮЛ (организации)
- /entrepreneur   — ЕГРИП (ИП)
- /person         — физические лица
- /finances       — финансовая отчетность
- /reliability    — оценка надежности
- /search         — поиск организаций/ИП
- /timeline       — история событий
- /legal-cases    — арбитражные дела
- /enforcements   — исполнительные производства (ФССП)
- /contracts      — госзакупки (44-ФЗ, 94-ФЗ, 223-ФЗ)
- /fedresurs      — сообщения Федресурса
- /bankruptcy-messages — записи ЕФРСБ
- /inspections    — проверки и КНМ
- /bank           — банки по БИК

Ограничения: 32 req/sec с одного IP, 100 бесплатных запросов/сутки.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class CheckoConnector(BaseConnector):
    """Коннектор для Checko API v2."""

    BASE_URL = "https://api.checko.ru/v2"

    ACTION_MAP = {
        "company": "_company",
        "entrepreneur": "_entrepreneur",
        "person": "_person",
        "finances": "_finances",
        "reliability": "_reliability",
        "search": "_search",
        "timeline": "_timeline",
        "legal-cases": "_legal_cases",
        "enforcements": "_enforcements",
        "contracts": "_contracts",
        "fedresurs": "_fedresurs",
        "bankruptcy-messages": "_bankruptcy_messages",
        "inspections": "_inspections",
        "bank": "_bank",
    }

    @property
    def name(self) -> str:
        return "checko"

    @property
    def rate_limit(self) -> int:
        return 32

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Роутер по action → приватный метод."""
        from person_osint.config import settings

        api_key = settings.checko_api_key
        if not api_key:
            # Configuration problem is not a successful skip — callers must see a real error.
            return self._missing_key_result()

        action = query.params.get("action", "company")
        method_name = self.ACTION_MAP.get(action)

        if not method_name:
            return ConnectorResult(
                success=False,
                source=self.name,
                error=f"Unknown action: {action}. Available: {list(self.ACTION_MAP.keys())}",
                error_code="unknown_action",
            )

        method = getattr(self, method_name)
        return await method(query.params, api_key)

    def _missing_key_result(self) -> ConnectorResult:
        return ConnectorResult(
            success=False,
            source=self.name,
            error="Проверка недоступна: ключ Checko не настроен",
            error_code="missing_api_key",
        )

    async def _request(self, endpoint: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
        """POST-запрос к Checko API."""
        client = await self.get_client()
        body = {"key": api_key}
        body.update(params)
        response = await client.post(f"{self.BASE_URL}/{endpoint}", json=body, timeout=30.0)
        response.raise_for_status()
        return response.json()

    # === 1. Company ===
    async def _company(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        elif params.get("okpo"):
            request_params["okpo"] = params["okpo"]
        if params.get("source"):
            request_params["source"] = "true"

        try:
            data = await self._request("company", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 2. Entrepreneur ===
    async def _entrepreneur(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        elif params.get("okpo"):
            request_params["okpo"] = params["okpo"]
        if params.get("source"):
            request_params["source"] = "true"

        try:
            data = await self._request("entrepreneur", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 3. Person ===
    async def _person(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]

        try:
            data = await self._request("person", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 4. Finances ===
    async def _finances(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        if params.get("extended"):
            request_params["extended"] = "true"

        try:
            data = await self._request("finances", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 5. Reliability ===
    async def _reliability(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]

        try:
            data = await self._request("reliability", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 6. Search ===
    async def _search(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        for key in ("by", "obj", "query", "region", "okved", "opf", "active", "codes", "limit", "page"):
            if params.get(key) is not None:
                request_params[key] = params[key]
                if key == "active" and isinstance(params[key], bool):
                    request_params[key] = "true" if params[key] else "false"

        try:
            data = await self._request("search", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 7. Timeline ===
    async def _timeline(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]

        try:
            data = await self._request("timeline", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 8. Legal Cases ===
    async def _legal_cases(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("role", "actual", "active", "date_from", "date_to",
                     "claim_amount_from", "claim_amount_to", "limit", "page", "sort"):
            if params.get(key) is not None:
                val = params[key]
                if isinstance(val, bool):
                    val = "true" if val else "false"
                request_params[key] = val

        try:
            data = await self._request("legal-cases", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 9. Enforcements ===
    async def _enforcements(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("limit", "page", "sort"):
            if params.get(key) is not None:
                request_params[key] = params[key]

        try:
            data = await self._request("enforcements", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 10. Contracts ===
    async def _contracts(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("law", "role", "limit", "page", "sort"):
            if params.get(key) is not None:
                request_params[key] = params[key]

        try:
            data = await self._request("contracts", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 11. Fedresurs ===
    async def _fedresurs(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("type", "role", "date_from", "date_to", "limit", "page", "sort"):
            if params.get(key) is not None:
                request_params[key] = params[key]

        try:
            data = await self._request("fedresurs", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 12. Bankruptcy Messages ===
    async def _bankruptcy_messages(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("date_from", "date_to", "limit", "page", "sort"):
            if params.get(key) is not None:
                request_params[key] = params[key]

        try:
            data = await self._request("bankruptcy-messages", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 13. Inspections ===
    async def _inspections(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("inn"):
            request_params["inn"] = params["inn"]
        elif params.get("ogrn"):
            request_params["ogrn"] = params["ogrn"]
        for key in ("limit", "page", "sort"):
            if params.get(key) is not None:
                request_params[key] = params[key]

        try:
            data = await self._request("inspections", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.9,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === 14. Bank ===
    async def _bank(self, params: dict[str, Any], api_key: str) -> ConnectorResult:
        request_params = {}
        if params.get("bic"):
            request_params["bic"] = params["bic"]

        try:
            data = await self._request("bank", request_params, api_key)
            return ConnectorResult(
                success=data.get("meta", {}).get("status") == "ok",
                data=data,
                source=self.name,
                confidence=0.95,
                error=data.get("meta", {}).get("message") or None,
            )
        except Exception as e:
            return ConnectorResult(success=False, source=self.name, error=str(e))

    # === Full Check — параллельная проверка 7 рисковых методов ===
    async def full_check(self, params: dict[str, Any]) -> dict[str, ConnectorResult]:
        """Комплексная проверка: company + reliability + legal-cases + enforcements + bankruptcy + fedresurs + inspections."""
        from person_osint.config import settings

        api_key = settings.checko_api_key
        if not api_key:
            return {"error": self._missing_key_result()}

        risk_methods = [
            ("company", self._company),
            ("reliability", self._reliability),
            ("legal_cases", self._legal_cases),
            ("enforcements", self._enforcements),
            ("bankruptcy_messages", self._bankruptcy_messages),
            ("fedresurs", self._fedresurs),
            ("inspections", self._inspections),
        ]

        async def _run(name: str, method) -> tuple[str, ConnectorResult]:
            result = await method(params, api_key)
            return name, result

        tasks = [_run(name, method) for name, method in risk_methods]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, ConnectorResult] = {}
        for item in results:
            if isinstance(item, Exception):
                output["unknown"] = ConnectorResult(success=False, source=self.name, error=str(item))
            else:
                name, result = item
                output[name] = result

        return output

    async def health_check(self) -> bool:
        """Проверка доступности API — запрос company по ИНН разработчика."""
        from person_osint.config import settings

        if not settings.checko_api_key:
            return False

        try:
            data = await self._request(
                "company",
                {"inn": "4027148080"},
                settings.checko_api_key,
            )
            return data.get("meta", {}).get("status") == "ok"
        except Exception:
            return False