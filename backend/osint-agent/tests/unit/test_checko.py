import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from osint_agent.config import settings
from osint_agent.connectors.checko import CheckoConnector
from osint_agent.models import ConnectorQuery

COMPANY = {
    "ИНН": "7707083893",
    "ОГРН": "1027700132195",
    "НаимСокр": "Тестовая компания",
    "НаимПолн": "Полное название",
    "ДатаРег": "1991-06-20",
    "Статус": {"Код": "001", "Наим": "Действует"},
    "ЮрАдрес": {"АдресРФ": "Москва", "Недост": False},
    "Руковод": [{"ФИО": "Иван Иванов", "ИНН": "123"}],
    "Учред": {"ФЛ": [{"ФИО": "Пётр Петров", "Доля": {"Процент": 25}}]},
    "Санкции": True,
}


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setattr(settings, "checko_api_key", SecretStr("test-secret"))
    monkeypatch.setattr("osint_agent.connectors.base.cache.get", AsyncMock(return_value=None))
    monkeypatch.setattr("osint_agent.connectors.base.cache.set", AsyncMock())
    monkeypatch.setattr("osint_agent.connectors.base.rate_limiter.wait", AsyncMock())


@pytest.mark.asyncio
async def test_company_normalization_and_secret_transport(configure):
    def handler(request):
        assert str(request.url) == "https://api.checko.ru/v2/company"
        assert json.loads(request.content) == {"key": "test-secret", "inn": "7707083893"}
        return httpx.Response(200, json={"meta": {"status": "ok"}, "data": COMPANY})

    connector = CheckoConnector()
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await connector.fetch(
            ConnectorQuery(query_type="company_legal", params={"inn": "7707083893"})
        )
    finally:
        await connector.close()
    assert result.success
    assert result.data["director"] == "Иван Иванов"
    assert result.data["shareholders"][0]["share_percent"] == 25
    assert result.data["risk_factors"]["sanctioned"] is True
    assert result.data["risk_factors"]["unfair_supplier"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"meta": {"status": "error", "message": "Bad key test-secret"}},
        {"meta": {"status": "ok"}, "data": None},
        {"meta": {"status": "ok"}, "data": {"ИНН": "another"}},
        {"meta": {"status": "ok"}, "data": [1]},
        ["unexpected"],
    ],
)
async def test_provider_errors_are_not_clean_checks(configure, payload):
    connector = CheckoConnector()
    connector._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    try:
        result = await connector.fetch(
            ConnectorQuery(query_type="company_legal", params={"inn": "7707083893"})
        )
    finally:
        await connector.close()
    assert not result.success
    assert "test-secret" not in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429, 503])
async def test_http_failure_does_not_expose_key(configure, status):
    connector = CheckoConnector()
    connector._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    try:
        result = await connector.fetch(
            ConnectorQuery(query_type="company_legal", params={"inn": "7707083893"})
        )
    finally:
        await connector.close()
    assert result.success is False
    assert "test-secret" not in result.error
    assert result.error


@pytest.mark.asyncio
async def test_entrepreneur_and_reliability_routes(configure):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        data = {"ИНН": "500100732259", "ФИО": "Иван Иванов", "ОГРНИП": "123"}
        return httpx.Response(200, json={"meta": {"status": "ok"}, "data": data})

    connector = CheckoConnector()
    connector._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await connector.fetch(
            ConnectorQuery(query_type="company_legal", params={"inn": "500100732259"})
        )
        reliability = await connector.fetch(
            ConnectorQuery(query_type="counterparty_reliability", params={"inn": "500100732259"})
        )
    finally:
        await connector.close()
    assert result.success and reliability.success
    assert result.data["entity_type"] == "entrepreneur"
    assert paths == ["/v2/entrepreneur", "/v2/reliability"]


@pytest.mark.asyncio
async def test_public_endpoint_and_graph_use_real_checko_once(configure, monkeypatch):
    from osint_agent.main import app

    calls = []

    async def fake_fetch(self, query):
        from osint_agent.models import ConnectorResult

        calls.append(query.query_type)
        return ConnectorResult(success=True, source="checko", data=self._normalize(COMPANY, False))

    monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/counterparties/7707083893")
        graph = await client.get("/api/v1/graph/7707083893")
        invalid = await client.get("/api/v1/counterparties/7707083894")
    assert response.status_code == graph.status_code == 200
    assert response.json()["company"]["risk_factors"]["sanctioned"] is True
    assert any(n["label"] == "Иван Иванов" for n in graph.json()["graph"]["nodes"])
    assert calls == ["company_legal", "company_legal"]
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_missing_key_and_invalid_inn_do_not_make_requests(monkeypatch):
    connector = CheckoConnector()
    monkeypatch.setattr(settings, "checko_api_key", SecretStr(""))
    result = await connector.fetch(
        ConnectorQuery(query_type="company_legal", params={"inn": "7707083893"})
    )
    assert not result.success
    monkeypatch.setattr(settings, "checko_api_key", SecretStr("test-secret"))
    result = await connector.fetch(
        ConnectorQuery(query_type="company_legal", params={"inn": "7707083894"})
    )
    assert not result.success
    assert connector._client is None


@pytest.mark.asyncio
async def test_optional_assessment_failure_preserves_company(configure, monkeypatch):
    from osint_agent.main import app
    from osint_agent.models import ConnectorResult

    async def fake_fetch(self, query):
        if query.query_type == "counterparty_reliability":
            return ConnectorResult(success=False, source="checko", error="Checko HTTP 403")
        return ConnectorResult(
            success=True, source="checko", data=self._normalize(COMPANY, False)
        )

    monkeypatch.setattr(CheckoConnector, "fetch", fake_fetch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/counterparties/7707083893", params={"include_reliability": "true"}
        )
    assert response.status_code == 200
    assert response.json()["company"]["inn"] == "7707083893"
    assert response.json()["reliability"]["success"] is False
    assert response.json()["reliability"]["error"] == "Checko HTTP 403"
