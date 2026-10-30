"""Tests for CheckoConnector."""

import pytest
import respx
from httpx import Response

from person_osint.connectors.checko import CheckoConnector
from person_osint.models import ConnectorQuery


@pytest.fixture
def connector():
    return CheckoConnector()


@pytest.fixture(autouse=True)
def mock_api_key(monkeypatch):
    monkeypatch.setattr("person_osint.config.settings.checko_api_key", "test-key-123")


class TestCheckoConnectorProperties:
    def test_name(self, connector):
        assert connector.name == "checko"

    def test_rate_limit(self, connector):
        assert connector.rate_limit == 32


class TestCheckoConnectorRouting:
    @pytest.mark.asyncio
    @respx.mock
    async def test_company_action(self, connector):
        respx.post("https://api.checko.ru/v2/company").mock(
            return_value=Response(200, json={
                "data": {"ОГРН": "1224000000278", "ИНН": "4027148080"},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "company", "inn": "4027148080"})
        result = await connector.execute(query)
        assert result.success is True
        assert result.source == "checko"

    @pytest.mark.asyncio
    @respx.mock
    async def test_entrepreneur_action(self, connector):
        respx.post("https://api.checko.ru/v2/entrepreneur").mock(
            return_value=Response(200, json={
                "data": {"ОГРНИП": "310402910200035", "ИНН": "402907671076"},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "entrepreneur", "inn": "402907671076"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_person_action(self, connector):
        respx.post("https://api.checko.ru/v2/person").mock(
            return_value=Response(200, json={
                "data": {"ИНН": "402907671076", "ФИО": "Иванов И.И."},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "person", "inn": "402907671076"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_finances_action(self, connector):
        respx.post("https://api.checko.ru/v2/finances").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7707049388"},
                "data": {"2023": {"1100": 1000000}},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "finances", "inn": "7707049388"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_reliability_action(self, connector):
        respx.post("https://api.checko.ru/v2/reliability").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7707049388"},
                "data": {"Масштаб": 85, "Баланс": {"Полож": 60, "ТрВним": 30, "Негатив": 10}},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "reliability", "inn": "7707049388"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_action(self, connector):
        respx.post("https://api.checko.ru/v2/search").mock(
            return_value=Response(200, json={
                "data": {"СтрВсего": 1, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={
            "action": "search", "by": "name", "obj": "org", "query": "Сбербанк"
        })
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeline_action(self, connector):
        respx.post("https://api.checko.ru/v2/timeline").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7724408012"},
                "data": [],
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "timeline", "inn": "7724408012"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_legal_cases_action(self, connector):
        respx.post("https://api.checko.ru/v2/legal-cases").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7804500856"},
                "data": {"ЗапВсего": 0, "СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "legal-cases", "inn": "7804500856"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_enforcements_action(self, connector):
        respx.post("https://api.checko.ru/v2/enforcements").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7707049388"},
                "data": {"СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "enforcements", "inn": "7707049388"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_contracts_action(self, connector):
        respx.post("https://api.checko.ru/v2/contracts").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7707049388"},
                "data": {"ЗапВсего": 0, "СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={
            "action": "contracts", "inn": "7707049388", "law": "44"
        })
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_fedresurs_action(self, connector):
        respx.post("https://api.checko.ru/v2/fedresurs").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7207018737"},
                "data": {"ЗапВсего": 0, "СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "fedresurs", "inn": "7207018737"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_bankruptcy_messages_action(self, connector):
        respx.post("https://api.checko.ru/v2/bankruptcy-messages").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7724408012"},
                "data": {"ЗапВсего": 0, "СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "bankruptcy-messages", "inn": "7724408012"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_inspections_action(self, connector):
        respx.post("https://api.checko.ru/v2/inspections").mock(
            return_value=Response(200, json={
                "company": {"ИНН": "7707049388"},
                "data": {"ЗапВсего": 0, "СтрВсего": 0, "СтрТекущ": 1, "Записи": []},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "inspections", "inn": "7707049388"})
        result = await connector.execute(query)
        assert result.success is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_bank_action(self, connector):
        respx.post("https://api.checko.ru/v2/bank").mock(
            return_value=Response(200, json={
                "data": {"БИК": "042908612", "Наим": "ПАО Сбербанк"},
                "meta": {"status": "ok"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "bank", "bic": "042908612"})
        result = await connector.execute(query)
        assert result.success is True


class TestCheckoConnectorErrors:
    @pytest.mark.asyncio
    async def test_unknown_action(self, connector):
        query = ConnectorQuery(query_type="checko", params={"action": "unknown_method"})
        result = await connector.execute(query)
        assert result.success is False
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_no_api_key(self, connector, monkeypatch):
        monkeypatch.setattr("person_osint.config.settings.checko_api_key", "")
        query = ConnectorQuery(query_type="checko", params={"action": "company", "inn": "123"})
        result = await connector.execute(query)
        assert result.success is False
        assert result.error_code == "missing_api_key"
        assert "ключ Checko не настроен" in result.error
        assert result.data is None

    @pytest.mark.asyncio
    async def test_no_api_key_full_check(self, connector, monkeypatch):
        monkeypatch.setattr("person_osint.config.settings.checko_api_key", "")
        results = await connector.full_check({"inn": "7707049388"})
        assert set(results.keys()) == {"error"}
        assert results["error"].error_code == "missing_api_key"

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_response(self, connector):
        respx.post("https://api.checko.ru/v2/company").mock(
            return_value=Response(200, json={
                "meta": {"status": "error", "message": "Organization not found"},
            })
        )
        query = ConnectorQuery(query_type="checko", params={"action": "company", "inn": "0000000000"})
        result = await connector.execute(query)
        assert result.success is False
        assert "Organization not found" in result.error

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error(self, connector):
        respx.post("https://api.checko.ru/v2/company").mock(
            return_value=Response(429, json={"error": "Rate limit exceeded"})
        )
        query = ConnectorQuery(query_type="checko", params={"action": "company", "inn": "123"})
        result = await connector.execute(query)
        assert result.success is False


class TestCheckoConnectorFullCheck:
    @pytest.mark.asyncio
    @respx.mock
    async def test_full_check(self, connector):
        ok_response = {"meta": {"status": "ok"}, "data": {}}
        for endpoint in ("company", "reliability", "legal-cases", "enforcements",
                         "bankruptcy-messages", "fedresurs", "inspections"):
            respx.post(f"https://api.checko.ru/v2/{endpoint}").mock(
                return_value=Response(200, json=ok_response)
            )

        results = await connector.full_check({"inn": "7707049388"})
        assert "company" in results
        assert "reliability" in results
        assert len(results) == 7
        for name, result in results.items():
            assert result.success is True, f"{name} failed: {result.error}"


class TestCheckoConnectorRequestFormat:
    @pytest.mark.asyncio
    @respx.mock
    async def test_request_includes_api_key(self, connector):
        route = respx.post("https://api.checko.ru/v2/company").mock(
            return_value=Response(200, json={"meta": {"status": "ok"}, "data": {}})
        )

        query = ConnectorQuery(query_type="checko", params={"action": "company", "inn": "4027148080"})
        await connector.execute(query)

        assert route.called
        body = route.calls.last.request.content
        assert b"test-key-123" in body
        assert b"4027148080" in body