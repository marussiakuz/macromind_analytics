"""Checko public routes: configuration failure must not look like success."""

import pytest
from httpx import ASGITransport, AsyncClient

from person_osint.main import app


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr("person_osint.config.settings.checko_api_key", "")


@pytest.mark.asyncio
async def test_person_route_without_key_returns_503(no_key):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/checko/person", json={"inn": "402907671076"})
    assert resp.status_code == 503
    assert "ключ Checko не настроен" in resp.json()["detail"]
    assert "skipped" not in resp.text


@pytest.mark.asyncio
async def test_company_route_without_key_returns_503(no_key):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/checko/company", json={"inn": "7707049388"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_search_route_without_key_returns_503(no_key):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/checko/search",
            json={"by": "name", "obj": "org", "query": "ростелеком"},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_full_check_without_key_returns_503_not_partial_ok(no_key):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/checko/full-check", json={"inn": "7707049388"})
    assert resp.status_code == 503
    assert resp.json().get("_status") is None
