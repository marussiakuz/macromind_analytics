"""Tests for person_legal and company_search branches used by the UI."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from osint_agent.config import settings
from osint_agent.connectors.checko import CheckoConnector
from osint_agent.models import ConnectorQuery

PERSON = {
    "ИНН": "402907671076",
    "ФИО": "Морозов Андрей Иванович",
    "Руковод": [
        {
            "ОГРН": "1027700132195",
            "ИНН": "7707083893",
            "НаимСокр": "Тест ООО",
            "НаимПолн": "Тестовое общество",
            "ДатаРег": "1991-06-20",
            "Статус": "Действует",
            "ЮрАдрес": "Москва",
            "ОКВЭД": "64.19",
        }
    ],
    "Учред": [
        {
            "ОГРН": "1102455001219",
            "ИНН": "7724408012",
            "НаимСокр": "Другая",
            "НаимПолн": "Другая компания",
            "Статус": "Действует",
        }
    ],
    "ИП": [
        {
            "ОГРНИП": "310402910200035",
            "ИНН": "402907671076",
            "ФИО": "Морозов Андрей Иванович",
            "Тип": "ИП",
            "ДатаРег": "2010-01-01",
            "Статус": "Действует",
            "ДатаПрекращ": None,
            "ОКВЭД": "62.01",
        }
    ],
    "ТоварЗнак": [{"ID": 1, "ДатаРег": "2020-01-01"}],
    "ЕФРСБ": [{"Тип": "Сообщение", "Дата": "2020-01-01", "Дело": "А40-1"}],
    "НедобПост": False,
    "МассРуковод": True,
    "МассУчред": False,
    "Санкции": True,
    "СанкцииСтраны": ["US"],
}

SEARCH_ORG = {
    "meta": {"status": "ok"},
    "data": {
        "СтрВсего": 3,
        "СтрТекущ": 1,
        "Записи": [
            {
                "ОГРН": "1027700132195",
                "ИНН": "7707083893",
                "КПП": "770701001",
                "НаимСокр": "ПАО СБЕРБАНК",
                "НаимПолн": "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО",
                "ДатаРег": "1991-06-20",
                "Статус": "Действует",
                "ДатаЛикв": None,
                "РегионКод": "77",
                "ЮрАдрес": "Москва",
                "ОКВЭД": "64.19",
            }
        ],
    },
}

SEARCH_ENT = {
    "meta": {"status": "ok"},
    "data": {
        "СтрВсего": 1,
        "СтрТекущ": 1,
        "Записи": [
            {
                "ОГРНИП": "310402910200035",
                "ИНН": "402907671076",
                "ФИО": "Морозов Андрей Иванович",
                "Тип": "ИП",
                "ДатаРег": "2010-01-01",
                "Статус": "Действует",
                "ДатаПрекращ": "2015-01-01",
                "РегионКод": "40",
                "ОКВЭД": "62.01",
            }
        ],
    },
}


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setattr(settings, "checko_api_key", SecretStr("test-key"))
    monkeypatch.setattr("osint_agent.connectors.base.cache.get", AsyncMock(return_value=None))
    monkeypatch.setattr("osint_agent.connectors.base.cache.set", AsyncMock())
    monkeypatch.setattr("osint_agent.connectors.base.rate_limiter.wait", AsyncMock())


def _connector(handler):
    connector = CheckoConnector()
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return connector


class TestPersonLegal:
    @pytest.mark.asyncio
    async def test_person_normalization(self, configure):
        def handler(request):
            assert request.url.path == "/v2/person"
            assert json.loads(request.content) == {"key": "test-key", "inn": "402907671076"}
            return httpx.Response(200, json={"meta": {"status": "ok"}, "data": PERSON})

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="person_legal", params={"inn": "402907671076"})
            )
        finally:
            await connector.close()
        assert result.success
        data = result.data
        assert data["inn"] == "402907671076"
        assert data["full_name"] == "Морозов Андрей Иванович"
        assert data["managed_companies"][0]["name"] == "Тест ООО"
        assert data["founded_companies"][0]["inn"] == "7724408012"
        assert data["entrepreneurships"][0]["ogrnip"] == "310402910200035"
        assert data["entrepreneurships"][0]["termination_date"] is None
        assert data["trademarks"][0]["ID"] == 1
        assert data["bankruptcy_messages"][0]["Дело"] == "А40-1"
        assert data["risk_factors"]["mass_director"] is True
        assert data["risk_factors"]["mass_founder"] is False
        assert data["risk_factors"]["unfair_supplier"] is False
        assert data["risk_factors"]["sanctioned_countries"] == ["US"]

    @pytest.mark.asyncio
    async def test_person_empty_lists_and_false_risks(self, configure):
        payload = dict(PERSON)
        payload = {
            "ИНН": "402907671076",
            "ФИО": "Иванов Иван",
            "Руковод": [],
            "Учред": [],
            "ИП": [],
            "ТоварЗнак": [],
            "ЕФРСБ": [],
            "МассРуковод": False,
            "МассУчред": False,
            "Санкции": False,
            "НедобПост": False,
        }
        connector = _connector(lambda r: httpx.Response(200, json={"meta": {"status": "ok"}, "data": payload}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="person_legal", params={"inn": "402907671076"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["managed_companies"] == []
        assert result.data["risk_factors"]["sanctioned"] is False

    @pytest.mark.asyncio
    async def test_person_inn_mismatch_is_error(self, configure):
        bad = dict(PERSON)
        bad["ИНН"] = "500100732259"
        connector = _connector(lambda r: httpx.Response(200, json={"meta": {"status": "ok"}, "data": bad}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="person_legal", params={"inn": "402907671076"})
            )
        finally:
            await connector.close()
        assert not result.success
        assert "другого ИНН" in result.error

    @pytest.mark.asyncio
    async def test_person_requires_12_digit_inn(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json={}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="person_legal", params={"inn": "7707083893"})
            )
        finally:
            await connector.close()
        assert not result.success


class TestCompanySearch:
    @pytest.mark.asyncio
    async def test_search_org_fields(self, configure):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=SEARCH_ORG)

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(
                    query_type="company_search",
                    params={"by": "name", "obj": "org", "query": "ростелеком", "limit": 5, "page": 2},
                )
            )
        finally:
            await connector.close()
        assert result.success
        assert captured["body"]["by"] == "name"
        assert captured["body"]["obj"] == "org"
        assert captured["body"]["limit"] == 5
        assert captured["body"]["page"] == 2
        row = result.data["results"][0]
        assert row["inn"] == "7707083893"
        assert row["ogrn"] == "1027700132195"
        assert row["name"] == "ПАО СБЕРБАНК"
        assert row["entity_type"] == "company"
        assert row["address"] == "Москва"
        assert result.data["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_search_ent_fields(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json=SEARCH_ENT))
        try:
            result = await connector.fetch(
                ConnectorQuery(
                    query_type="company_search",
                    params={"by": "name", "obj": "ent", "query": "морозов"},
                )
            )
        finally:
            await connector.close()
        row = result.data["results"][0]
        assert row["ogrn"] == "310402910200035"
        assert row["name"] == "Морозов Андрей Иванович"
        assert row["entity_type"] == "entrepreneur"
        assert row["liquidation_date"] == "2015-01-01"

    @pytest.mark.asyncio
    async def test_active_false_is_passed(self, configure):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=SEARCH_ORG)

        connector = _connector(handler)
        try:
            await connector.fetch(
                ConnectorQuery(
                    query_type="company_search",
                    params={"by": "name", "obj": "org", "query": "тест", "active": False},
                )
            )
        finally:
            await connector.close()
        assert captured["body"]["active"] == "false"

    @pytest.mark.asyncio
    async def test_okved_short_query_accepted(self, configure):
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"meta": {"status": "ok"}, "data": {"Записи": []}})

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_search", params={"by": "okved", "obj": "org", "query": "62"})
            )
        finally:
            await connector.close()
        assert result.success
        assert captured["body"]["query"] == "62"
        assert captured["body"]["by"] == "okved"
        assert result.data["results"] == []

    @pytest.mark.asyncio
    async def test_name_short_query_rejected(self, configure):
        called = False

        def handler(request):
            nonlocal called
            called = True
            return httpx.Response(200, json={})

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_search", params={"by": "name", "obj": "org", "query": "abc"})
            )
        finally:
            await connector.close()
        assert not result.success
        assert called is False

    @pytest.mark.asyncio
    async def test_meta_error_and_bad_json(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json={"meta": {"status": "error", "message": "Bad"}}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_search", params={"by": "name", "obj": "org", "query": "тест"})
            )
        finally:
            await connector.close()
        assert not result.success

        connector = _connector(lambda r: httpx.Response(200, text="not-json"))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_search", params={"by": "name", "obj": "org", "query": "тест"})
            )
        finally:
            await connector.close()
        assert not result.success


class TestCompanyFinances:
    FINANCES = {
        "company": {"ИНН": "7707049388", "ОГРН": "1027700198767", "НаимСокр": "ПАО Ростелеком"},
        "data": {
            "2021": {"2110": 550_000_000_000, "2400": 30_000_000_000, "1100": 1},
            "2022": {"2110": 590_000_000_000, "2400": -1_000_000_000},
            "2023": {"2110": 640_000_000_000, "2400": 22_000_000_000},
        },
        "bo.nalog.ru": {"ID": 1, "Отчет": {"2023": "https://bo.nalog.gov.ru/1.pdf"}},
        "meta": {"status": "ok"},
    }

    @pytest.mark.asyncio
    async def test_finances_normalization_standard(self, configure):
        def handler(request):
            body = json.loads(request.content)
            assert body["inn"] == "7707049388"
            assert request.url.path == "/v2/finances"
            return httpx.Response(200, json=self.FINANCES)

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_finances", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        years = {y["year"]: y for y in result.data["years"]}
        assert years[2022]["revenue"] == 590_000_000_000
        assert years[2022]["net_profit"] == -1_000_000_000
        assert result.data["report_links"]["2023"].startswith("https://")
        assert result.data["inn"] == "7707049388"

    @pytest.mark.asyncio
    async def test_finances_extended_uses_sum_otch(self, configure):
        payload = {
            "company": {"ИНН": "7707049388"},
            "data": {
                "2023": {
                    "2110": {"СумОтч": 100, "СумПрдщ": 90, "СумПрдшв": 80},
                    "2400": {"СумОтч": 10, "СумПрдщ": 5, "СумПрдшв": 1},
                }
            },
            "meta": {"status": "ok"},
        }
        connector = _connector(lambda r: httpx.Response(200, json=payload))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_finances", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["years"][0]["revenue"] == 100
        assert result.data["years"][0]["net_profit"] == 10

    @pytest.mark.asyncio
    async def test_finances_empty_years_is_success(self, configure):
        payload = {"company": {"ИНН": "7707049388"}, "data": {}, "meta": {"status": "ok"}}
        connector = _connector(lambda r: httpx.Response(200, json=payload))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_finances", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["years"] == []

    @pytest.mark.asyncio
    async def test_finances_requires_company_inn(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json={}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_finances", params={"inn": "770303580308"})
            )
        finally:
            await connector.close()
        assert not result.success

    @pytest.mark.asyncio
    async def test_finances_route(self, configure, monkeypatch):
        from osint_agent.main import app

        async def fake_fetch(self, query):
            from osint_agent.models import ConnectorResult

            return ConnectorResult(
                success=True,
                source="checko",
                data={"inn": "7707049388", "years": [{"year": 2023, "revenue": 1, "net_profit": 2}]},
            )

        monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/companies/7707049388/finances")
            assert resp.status_code == 200
            assert resp.json()["finances"]["years"][0]["year"] == 2023
            bad = await client.get("/api/v1/companies/770303580308/finances")
            assert bad.status_code == 400


class TestCompanyTimeline:
    TIMELINE = {
        "company": {"ИНН": "7707049388", "ОГРН": "1027700198767", "НаимСокр": "ПАО Ростелеком"},
        "data": [
            {"Дата": "2020-01-15", "Событие": "Изменение адреса"},
            {"Дата": "2021-06-01", "Событие": "Смена руководителя"},
        ],
        "meta": {"status": "ok"},
    }

    @pytest.mark.asyncio
    async def test_timeline_normalization(self, configure):
        def handler(request):
            assert request.url.path == "/v2/timeline"
            assert json.loads(request.content) == {"key": "test-key", "inn": "7707049388"}
            return httpx.Response(200, json=self.TIMELINE)

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_timeline", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["inn"] == "7707049388"
        assert result.data["events"][0]["date"] == "2020-01-15"
        assert result.data["events"][1]["event"] == "Смена руководителя"

    @pytest.mark.asyncio
    async def test_timeline_empty_is_success(self, configure):
        payload = {"company": {"ИНН": "7707049388"}, "data": [], "meta": {"status": "ok"}}
        connector = _connector(lambda r: httpx.Response(200, json=payload))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_timeline", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["events"] == []

    @pytest.mark.asyncio
    async def test_timeline_person_payload(self, configure):
        payload = {
            "person": {"ИНН": "770303580308", "ФИО": "Греф Герман"},
            "data": [{"Дата": "2022-01-01", "Событие": "Вход в состав"}],
            "meta": {"status": "ok"},
        }
        connector = _connector(lambda r: httpx.Response(200, json=payload))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_timeline", params={"inn": "770303580308"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["entity_type"] == "person"
        assert result.data["name"] == "Греф Герман"

    @pytest.mark.asyncio
    async def test_timeline_bad_structure(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json={"data": {"x": 1}, "meta": {"status": "ok"}}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_timeline", params={"inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert not result.success

    @pytest.mark.asyncio
    async def test_timeline_route(self, configure, monkeypatch):
        from osint_agent.main import app

        async def fake_fetch(self, query):
            from osint_agent.models import ConnectorResult

            return ConnectorResult(
                success=True,
                source="checko",
                data={"inn": "7707049388", "events": [{"date": "2020-01-15", "event": "Тест"}]},
            )

        monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/companies/7707049388/timeline")
            assert resp.status_code == 200
            assert resp.json()["timeline"]["events"][0]["event"] == "Тест"
            bad = await client.get("/api/v1/companies/abc/timeline")
            assert bad.status_code == 400


class TestCompanyRegistry:
    LEGAL = {
        "company": {"ИНН": "7707049388", "НаимСокр": "ПАО Ростелеком"},
        "data": {
            "ЗапВсего": 2,
            "СтрВсего": 1,
            "ОбщСуммИск": 100.0,
            "Записи": [
                {
                    "Номер": "А40-1",
                    "UUID": "u-1",
                    "СтрКАД": "https://kad.arbitr.ru/1",
                    "Дата": "2024-01-10",
                    "Тип": "Г",
                    "ПрАктив": True,
                    "Суд": "АС г. Москвы",
                    "Ист": [{"Наим": "ООО Истец", "ИНН": "1"}],
                    "Ответ": [{"Наим": "ПАО Ростелеком", "ИНН": "7707049388"}],
                    "СуммИск": 50.0,
                    "ИсходТекст": "Решение принято",
                    "Победитель": "Истец",
                }
            ],
        },
        "meta": {"status": "ok"},
    }

    ENF = {
        "company": {"ИНН": "7707049388"},
        "data": {
            "Записи": [
                {
                    "ИспПрНомер": "123",
                    "ИспПрДата": "2023-05-01",
                    "ПредмИсп": "Взыскание долга",
                    "СумДолг": 10.0,
                    "ОстЗадолж": 5.0,
                    "ДолжНаим": "ПАО Ростелеком",
                }
            ]
        },
        "meta": {"status": "ok"},
    }

    CONTRACTS = {
        "company": {"ИНН": "7707049388"},
        "data": {
            "Записи": [
                {
                    "РегНомер": "123",
                    "СтрЕИС": "https://zakupki.gov.ru/1",
                    "Дата": "2022-01-01",
                    "Цена": 1000,
                    "Заказ": {"НаимСокр": "Заказчик", "ИНН": "1"},
                    "Постав": [{"НаимСокр": "Поставщик", "ИНН": "2"}],
                    "Объекты": [{"Наим": "Услуги"}],
                }
            ]
        },
        "meta": {"status": "ok"},
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method,payload,check",
        [
            ("legal-cases", LEGAL, lambda r: r["items"][0]["title"] == "Дело №А40-1"),
            ("enforcements", ENF, lambda r: r["items"][0]["fields"]["Остаток"] == 5.0),
            ("contracts", CONTRACTS, lambda r: r["items"][0]["fields"]["Заказчик"] == "Заказчик"),
        ],
    )
    async def test_registry_normalize(self, configure, method, payload, check):
        def handler(request):
            body = json.loads(request.content)
            assert body["inn"] == "7707049388"
            return httpx.Response(200, json=payload)

        connector = _connector(handler)
        try:
            result = await connector.fetch(
                ConnectorQuery(
                    query_type="company_registry",
                    params={"method": method, "inn": "7707049388", "law": "44" if method == "contracts" else None},
                )
            )
        finally:
            await connector.close()
        assert result.success
        assert check(result.data)

    @pytest.mark.asyncio
    async def test_registry_invalid_method(self, configure):
        connector = _connector(lambda r: httpx.Response(200, json={}))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_registry", params={"method": "nope", "inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert not result.success

    @pytest.mark.asyncio
    async def test_registry_empty_items(self, configure):
        payload = {"company": {"ИНН": "7707049388"}, "data": {"Записи": []}, "meta": {"status": "ok"}}
        connector = _connector(lambda r: httpx.Response(200, json=payload))
        try:
            result = await connector.fetch(
                ConnectorQuery(query_type="company_registry", params={"method": "inspections", "inn": "7707049388"})
            )
        finally:
            await connector.close()
        assert result.success
        assert result.data["items"] == []

    @pytest.mark.asyncio
    async def test_registry_route_requires_law_for_contracts(self, configure, monkeypatch):
        from osint_agent.main import app

        async def fake_fetch(self, query):
            from osint_agent.models import ConnectorResult

            return ConnectorResult(success=True, source="checko", data={"inn": "7707049388", "items": []})

        monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            ok = await client.get("/api/v1/companies/7707049388/registry/legal-cases")
            assert ok.status_code == 200
            no_law = await client.get("/api/v1/companies/7707049388/registry/contracts")
            assert no_law.status_code == 400
            with_law = await client.get(
                "/api/v1/companies/7707049388/registry/contracts", params={"law": "44"}
            )
            assert with_law.status_code == 200
            bad_method = await client.get("/api/v1/companies/7707049388/registry/unknown")
            assert bad_method.status_code == 400


class TestSearchRoutes:
    @pytest.mark.asyncio
    async def test_search_route_ok_and_validation(self, configure, monkeypatch):
        from osint_agent.main import app

        async def fake_fetch(self, query):
            from osint_agent.models import ConnectorResult

            return ConnectorResult(
                success=True,
                source="checko",
                data={
                    "by": query.params.get("by"),
                    "obj": query.params.get("obj"),
                    "query": query.params.get("query"),
                    "total_pages": 1,
                    "page": query.params.get("page") or 1,
                    "results": [{"inn": "7707083893", "name": "ПАО СБЕРБАНК", "entity_type": "company"}],
                    "source": "checko",
                },
            )

        monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            ok = await client.get("/api/v1/companies/search", params={"q": "62", "by": "okved"})
            assert ok.status_code == 200
            assert ok.json()["by"] == "okved"
            short_name = await client.get("/api/v1/companies/search", params={"q": "abc", "by": "name"})
            assert short_name.status_code == 400
            empty = await client.get("/api/v1/companies/search", params={"q": "   ", "by": "name"})
            assert empty.status_code == 400

    @pytest.mark.asyncio
    async def test_person_route_ok(self, configure, monkeypatch):
        from osint_agent.main import app

        async def fake_fetch(self, query):
            from osint_agent.models import ConnectorResult

            return ConnectorResult(
                success=True,
                source="checko",
                data={"inn": "402907671076", "full_name": "Тест", "entity_type": "person"},
            )

        monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/persons/402907671076")
            assert resp.status_code == 200
            assert resp.json()["person"]["inn"] == "402907671076"
            bad = await client.get("/api/v1/persons/7707083893")
            assert bad.status_code == 400
