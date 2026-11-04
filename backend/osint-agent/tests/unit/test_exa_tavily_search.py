"""Exa / Tavily adapters, factory and managed fallback (MIMO_EXA_SETUP / MIMO_TAVILY_SETUP)."""

import httpx
import pytest

from osint_agent.market.providers.base import SourceStatus
from osint_agent.market.providers.exa_search import EXA_SEARCH_URL, ExaSearchProvider
from osint_agent.market.providers.search_fallback import FallbackSearchProvider
from osint_agent.market.providers.tavily_search import TAVILY_SEARCH_URL, TavilySearchProvider


def _exa_payload(**over):
    payload = {
        "requestId": "req-1",
        "searchTime": 0.5,
        "costDollars": {"total": 0.007},
        "results": [
            {
                "id": "exa-id-1",
                "url": "https://tota.systems/products",
                "title": "ТОТА СИСТЕМС",
                "publishedDate": "2025-06-01",
                "score": 0.91,
                "highlights": ["Системы мониторинга состояния машин", "Поставка датчиков"],
            },
            {"id": "exa-id-2", "url": "https://example.com/x", "title": "No text"},
        ],
    }
    payload.update(over)
    return payload


def _tavily_payload(**over):
    payload = {
        "query": "q",
        "response_time": 2.02,
        "request_id": "tv-1",
        "usage": {"credits": 2},
        "results": [
            {
                "id": "tv-id-1",
                "url": "https://tota.systems/products",
                "title": "ТОТА СИСТЕМС",
                "content": "Системы мониторинга состояния машин",
                "score": 0.81,
            },
            {"id": "tv-id-2", "url": "https://example.com/x", "title": "No content"},
        ],
    }
    payload.update(over)
    return payload


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- Exa: успех и нормализация ---


@pytest.mark.asyncio
async def test_exa_success_normalizes_fields_and_budget():
    captured = {}

    def handler(request):
        import json

        assert request.url == EXA_SEARCH_URL
        assert request.headers.get("x-api-key") == "test-key"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_exa_payload())

    p = ExaSearchProvider(api_key="test-key", client=_client(handler))
    try:
        page = await p.search("ТОТА продукция", budget=2)
    finally:
        await p.aclose()
    assert page.status == SourceStatus.ok
    assert page.source == "exa_search"
    assert page.cursor is None  # Search не поддерживает пагинацию
    assert captured["body"]["numResults"] == 2
    assert captured["body"]["contents"] == {"highlights": True}
    assert captured["body"]["type"] == "auto"
    assert "category" not in captured["body"] and "includeDomains" not in captured["body"]
    item = page.items[0]
    assert item["url"] == "https://tota.systems/products"
    assert item["highlights"] == ["Системы мониторинга состояния машин", "Поставка датчиков"]
    assert item["published_date"] == "2025-06-01"
    assert item["id"] == "exa-id-1"
    assert item["score"] == 0.91
    assert item["passage"] == "Системы мониторинга состояния машин\nПоставка датчиков"
    # метаданные без текста сохраняются честно
    assert page.items[1]["passage"] == ""
    assert page.items[1]["published_date"] is None
    assert "costDollars" in page.coverage and "searchTime" in page.coverage


@pytest.mark.asyncio
async def test_exa_empty_results_is_empty_status():
    def handler(request):
        return httpx.Response(200, json=_exa_payload(results=[]))

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.empty
    assert page.items == []


@pytest.mark.asyncio
async def test_exa_missing_key_is_not_configured():
    p = ExaSearchProvider(api_key="")
    page = await p.search("q")
    assert page.status == SourceStatus.not_configured
    assert page.error_code == "not_configured"
    assert "test" not in page.message.lower() or "key" in page.message.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expect_status,expect_code",
    [
        (401, SourceStatus.error, "auth_error"),
        (403, SourceStatus.error, "auth_error"),
        (402, SourceStatus.error, "payment_required"),
        (429, SourceStatus.rate_limited, "rate_limited"),
        (500, SourceStatus.unavailable, "unavailable"),
    ],
)
async def test_exa_http_error_states(status, expect_status, expect_code):
    def handler(request):
        return httpx.Response(status, json={"error": "secret-detail"})

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == expect_status
    assert page.error_code == expect_code
    assert "secret-detail" not in (page.message or "")


@pytest.mark.asyncio
async def test_exa_bad_json_is_format_error():
    def handler(request):
        return httpx.Response(200, content=b"not-json")

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.error
    assert page.error_code == "format_error"


@pytest.mark.asyncio
async def test_exa_broken_structure_is_format_error():
    def handler(request):
        return httpx.Response(200, json={"results": "oops"})

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.error
    assert page.error_code == "format_error"


@pytest.mark.asyncio
async def test_exa_timeout_is_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("t")

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.unavailable


@pytest.mark.asyncio
async def test_exa_zero_budget_does_not_touch_network():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json=_exa_payload())

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q", budget=0)
    finally:
        await p.aclose()
    assert calls == []
    assert page.status == SourceStatus.empty


@pytest.mark.asyncio
async def test_exa_num_results_clamped():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_exa_payload(results=[]))

    p = ExaSearchProvider(api_key="k", client=_client(handler))
    try:
        await p.search("q", budget=500)
    finally:
        await p.aclose()
    assert captured["body"]["numResults"] == 100


@pytest.mark.asyncio
async def test_exa_hides_secret_and_does_not_close_injected_client():
    def handler(request):
        return httpx.Response(200, json=_exa_payload())

    client = _client(handler)
    p = ExaSearchProvider(api_key="super-secret-key", client=client)
    page = await p.search("q")
    await p.aclose()
    assert "super-secret-key" not in (page.message or "")
    assert "super-secret-key" not in (page.coverage or "")
    assert not client.is_closed  # чужой клиент не закрываем
    owned = ExaSearchProvider(api_key="k")
    oc = await owned._get_client()
    await owned.aclose()
    assert oc.is_closed


# --- Tavily ---


@pytest.mark.asyncio
async def test_tavily_success_normalizes_fields():
    captured = {}

    def handler(request):
        import json

        assert request.url == TAVILY_SEARCH_URL
        assert request.headers.get("Authorization") == "Bearer test-key"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_tavily_payload())

    p = TavilySearchProvider(api_key="test-key", client=_client(handler), search_depth="advanced")
    try:
        page = await p.search("Tota Systems", budget=5)
    finally:
        await p.aclose()
    assert page.status == SourceStatus.ok
    assert page.source == "tavily_search"
    assert page.cursor is None
    body = captured["body"]
    assert body["search_depth"] == "advanced"
    assert body["max_results"] == 5
    assert body["include_answer"] is False and body["include_usage"] is True
    assert "auto_parameters" not in body
    item = page.items[0]
    assert item["content"] == "Системы мониторинга состояния машин"
    assert item["passage"] == item["content"]
    assert item["score"] == 0.81
    assert item["published_date"] is None  # нет published_date → не подменяем
    assert page.items[1]["passage"] == ""
    assert "credits=2" in page.coverage and "search_depth=advanced" in page.coverage


@pytest.mark.asyncio
async def test_tavily_zero_budget_no_network_and_clamp():
    calls = []

    def handler(request):
        import json

        calls.append(json.loads(request.content))
        return httpx.Response(200, json=_tavily_payload(results=[]))

    p = TavilySearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q", budget=0)
        assert page.status == SourceStatus.empty and calls == []
        await p.search("q", budget=50)
    finally:
        await p.aclose()
    assert calls[0]["max_results"] == 20  # документированный максимум


@pytest.mark.asyncio
async def test_tavily_empty_results():
    def handler(request):
        return httpx.Response(200, json=_tavily_payload(results=[]))

    p = TavilySearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.empty


@pytest.mark.asyncio
async def test_tavily_missing_key():
    p = TavilySearchProvider(api_key="")
    page = await p.search("q")
    assert page.status == SourceStatus.not_configured
    assert page.error_code == "not_configured"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expect_status,expect_code",
    [
        (401, SourceStatus.error, "auth_error"),
        (403, SourceStatus.error, "auth_error"),
        (432, SourceStatus.error, "credits_exhausted"),
        (433, SourceStatus.error, "credits_exhausted"),
        (429, SourceStatus.rate_limited, "rate_limited"),
        (434, SourceStatus.unavailable, "unavailable"),
        (500, SourceStatus.unavailable, "unavailable"),
    ],
)
async def test_tavily_http_error_states(status, expect_status, expect_code):
    def handler(request):
        return httpx.Response(status, json={"detail": {"error": "secret-detail"}})

    p = TavilySearchProvider(api_key="k", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == expect_status
    assert page.error_code == expect_code
    assert "secret-detail" not in (page.message or "")


@pytest.mark.asyncio
async def test_tavily_bad_json_and_broken_structure():
    def bad(request):
        return httpx.Response(200, content=b"not-json")

    def broken(request):
        return httpx.Response(200, json={"results": {"a": 1}})

    p = TavilySearchProvider(api_key="k", client=_client(bad))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.error_code == "format_error"

    p = TavilySearchProvider(api_key="k", client=_client(broken))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.error_code == "format_error"


@pytest.mark.asyncio
async def test_tavily_timeout_and_secret_hidden():
    def handler(request):
        raise httpx.ReadTimeout("t")

    p = TavilySearchProvider(api_key="tvly-secret", client=_client(handler))
    try:
        page = await p.search("q")
    finally:
        await p.aclose()
    assert page.status == SourceStatus.unavailable
    assert "tvly-secret" not in (page.message or "")


# --- Управляемое резервирование ---


class _FakeProvider:
    def __init__(self, name, page):
        self.name = name
        self.page = page
        self.calls = []
        self.closed = False

    async def search(self, query, **kw):
        self.calls.append(query)
        return self.page

    async def aclose(self):
        self.closed = True


def _page(status, source, items=None, message=None, error_code=None):
    from osint_agent.market.providers.base import SearchPage

    return SearchPage(items=items or [], status=status, source=source,
                      message=message, error_code=error_code)


@pytest.mark.asyncio
async def test_fallback_switches_on_primary_failure_and_keeps_reason():
    primary = _FakeProvider("exa_search", _page(SourceStatus.unavailable, "exa_search",
                                                message="Exa HTTP 500", error_code="unavailable"))
    backup = _FakeProvider("tavily_search", _page(SourceStatus.ok, "tavily_search",
                                                  items=[{"url": "https://a.ru", "title": "A", "passage": "x"}]))
    fb = FallbackSearchProvider(primary, backup, max_backup_queries=2)
    page = await fb.search("q")
    assert page.source == "tavily_search"  # фактический источник результатов
    assert page.items and page.status == SourceStatus.ok
    assert "exa_search" in page.message and "unavailable" in page.message
    assert backup.calls == ["q"]


@pytest.mark.asyncio
async def test_fallback_not_used_on_ok_or_empty():
    for status in (SourceStatus.ok, SourceStatus.empty, SourceStatus.partial):
        primary = _FakeProvider("exa_search", _page(status, "exa_search"))
        backup = _FakeProvider("tavily_search", _page(SourceStatus.ok, "tavily_search", items=[{"url": "u"}]))
        fb = FallbackSearchProvider(primary, backup)
        await fb.search("q")
        assert backup.calls == [], status


@pytest.mark.asyncio
async def test_fallback_budget_exhausted_keeps_primary_state():
    primary = _FakeProvider("exa_search", _page(SourceStatus.error, "exa_search",
                                                message="Exa HTTP 503", error_code="unavailable"))
    backup = _FakeProvider("tavily_search", _page(SourceStatus.ok, "tavily_search", items=[{"url": "u"}]))
    fb = FallbackSearchProvider(primary, backup, max_backup_queries=0)
    page = await fb.search("q")
    assert backup.calls == []
    assert page.source == "exa_search"
    assert "Exa HTTP 503" in page.message and "резерв не использован" in page.message


@pytest.mark.asyncio
async def test_fallback_search_backup_uses_shared_counter():
    backup = _FakeProvider("tavily_search", _page(SourceStatus.ok, "tavily_search", items=[{"url": "u"}]))
    primary = _FakeProvider("exa_search", _page(SourceStatus.ok, "exa_search"))
    fb = FallbackSearchProvider(primary, backup, max_backup_queries=2)
    r1 = await fb.search_backup("конкретный запрос 1")
    r2 = await fb.search_backup("конкретный запрос 2")
    r3 = await fb.search_backup("третий")
    assert r1.status == SourceStatus.ok and r2.status == SourceStatus.ok
    assert r3.error_code == "backup_budget_exhausted"
    assert backup.calls == ["конкретный запрос 1", "конкретный запрос 2"]


@pytest.mark.asyncio
async def test_fallback_backup_budget_via_research_budget():
    from osint_agent.market.research_budget import ResearchBudget

    backup = _FakeProvider("tavily_search", _page(SourceStatus.ok, "tavily_search", items=[{"url": "u"}]))
    primary = _FakeProvider("exa_search", _page(SourceStatus.unavailable, "exa_search"))
    budget = ResearchBudget(max_backup_search=1)
    fb = FallbackSearchProvider(primary, backup, budget=budget)
    await fb.search("q1")
    await fb.search("q2")  # остаточный бюджет исчерпан — резерв не вызывается
    assert backup.calls == ["q1"]
    assert budget.used_backup_search == 1
    assert budget.used_search == 1  # расход учтён в общем бюджете


# --- Фабрика ---


@pytest.mark.asyncio
async def test_factory_branches_and_unknown_error(monkeypatch):
    from osint_agent.config import settings
    from osint_agent.market.providers import search_factory

    monkeypatch.setattr(settings, "search_provider", "exa")
    assert search_factory.get_search_provider().name == "exa_search"
    monkeypatch.setattr(settings, "search_provider", "tavily")
    assert search_factory.get_search_provider().name == "tavily_search"
    monkeypatch.setattr(settings, "search_provider", "yandex")
    assert search_factory.get_search_provider().name == "yandex_search"
    monkeypatch.setattr(settings, "search_provider", "brave")
    with pytest.raises(ValueError) as exc:
        search_factory.get_search_provider()
    assert "brave" in str(exc.value) and "exa" in str(exc.value)
    monkeypatch.setattr(settings, "search_provider", "")
    with pytest.raises(ValueError):
        search_factory.get_search_provider()


@pytest.mark.asyncio
async def test_factory_wraps_fallback_only_when_enabled(monkeypatch):
    from osint_agent.config import settings
    from osint_agent.market.providers import search_factory

    monkeypatch.setattr(settings, "search_provider", "exa")
    monkeypatch.setattr(settings, "search_fallback", False)
    assert search_factory.get_search_provider().name == "exa_search"
    monkeypatch.setattr(settings, "search_fallback", True)
    monkeypatch.setattr(settings, "search_fallback_provider", "tavily")
    wrapped = search_factory.get_search_provider()
    assert isinstance(wrapped, FallbackSearchProvider)
    assert wrapped.primary.name == "exa_search" and wrapped.backup.name == "tavily_search"
    # без повторного оборачивания, когда запасной совпадает с основным
    monkeypatch.setattr(settings, "search_provider", "tavily")
    assert search_factory.get_search_provider().name == "tavily_search"


# --- Происхождение источников до фактуры ---


def test_evidence_from_search_keeps_actual_provider():
    from osint_agent.market.evidence import _evidence_from_search

    items = [
        {"url": "https://tota.systems", "title": "ТОТА", "highlights": ["выдержка"], "published_date": "2025-01-01"},
        {"url": "https://example.com/meta", "title": "Без текста"},
    ]
    rows = _evidence_from_search(items, "q", "exa_search")
    assert rows[0]["id"].startswith("exa:")
    assert rows[0]["source_id"] == "exa_search"
    assert rows[0]["quote"] == "выдержка"
    assert rows[0]["publication_date"] == "2025-01-01"
    assert rows[1]["read_level"] == "metadata_only"
    assert rows[1]["quote"] == ""
    rows = _evidence_from_search(items, "q", "tavily_search")
    assert rows[0]["id"].startswith("tavily:")
    assert rows[0]["source_id"] == "tavily_search"


def test_evidence_from_search_backward_compat_yandex_ids():
    from osint_agent.market.evidence import _evidence_from_search

    rows = _evidence_from_search([{"url": "https://a.ru", "title": "A", "passage": "p"}], "q", "yandex_search")
    assert rows[0]["id"].startswith("yandex:")
    assert rows[0]["source_id"] == "yandex_search"


def test_url_dedupe_does_not_double_confirm():
    from osint_agent.market.evidence import _dedupe_by_url, normalize_url_key

    assert normalize_url_key("HTTPS://Tota.Systems/products/") == normalize_url_key("https://tota.systems/products")
    rows = [
        {"id": "exa:1", "url": "https://tota.systems/products/"},
        {"id": "tavily:2", "url": "https://tota.systems/products"},
        {"id": "exa:3", "url": "https://other.example/x"},
    ]
    unique, dup = _dedupe_by_url(rows)
    assert dup == 1
    assert rows[1].get("duplicate_of") == "exa:1"
    assert len(unique) == 2
