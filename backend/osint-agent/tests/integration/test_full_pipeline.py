"""Integration tests — полный цикл через mock-коннекторы.

Проверяет склейку компонентов:
  Hub → Connector → GraphBuilder → Graph API → vis.js JSON

Каждый тест проверяет один сценарий сквозного пайплайна.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.egrul import MockEGRULConnector
from osint_agent.connectors.whois import MockWhoisConnector
from osint_agent.connectors.dns import MockDNSConnector
from osint_agent.connectors.shodan import MockShodanConnector
from osint_agent.connectors.document import MockDocumentConnector
from osint_agent.connectors.mock import (
    MockSanctionConnector,
    MockNewsConnector,
    MockPEPConnector,
    MockSocialConnector,
    MockFNSTaxConnector,
    MockKADConnector,
    MockFSSPConnector,
)
from osint_agent.graph import RelationshipGraph
from osint_agent.graph.builder import CompanyGraphBuilder
from osint_agent.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_full_hub() -> DataConnectorHub:
    """Hub со всеми mock-коннекторами."""
    hub = DataConnectorHub()
    hub.register(MockEGRULConnector())
    hub.register(MockWhoisConnector())
    hub.register(MockDNSConnector())
    hub.register(MockShodanConnector())
    hub.register(MockDocumentConnector())
    hub.register(MockSanctionConnector())
    hub.register(MockNewsConnector())
    hub.register(MockPEPConnector())
    hub.register(MockSocialConnector())
    hub.register(MockFNSTaxConnector())
    hub.register(MockKADConnector())
    hub.register(MockFSSPConnector())
    return hub


@pytest.fixture
def hub():
    return _build_full_hub()


@pytest.fixture
def builder(hub):
    return CompanyGraphBuilder(hub)


@pytest.fixture
def api_client():
    """FastAPI TestClient с mock hub."""
    transport = ASGITransport(app=app)
    with patch("osint_agent.api.graph._build_hub", _build_full_hub):
        yield AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Hub → Connector: fallback chain
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHubFallbackChain:
    """Hub корректно маршрутизирует запросы через fallback chain."""

    @pytest.mark.asyncio
    async def test_whois_fallback(self, hub):
        """Hub находит whois-коннектор через fallback chain."""
        result = await hub.fetch("whois", {"domain": "test-company.ru"})
        assert result.success
        assert result.data["domain"] == "test-company.ru"
        assert "registrar" in result.data

    @pytest.mark.asyncio
    async def test_dns_fallback(self, hub):
        """Hub находит dns-коннектор."""
        result = await hub.fetch("dns", {"domain": "ya.ru"})
        assert result.success
        assert "records" in result.data
        assert result.data["records"]["A"] == ["5.255.255.80"]

    @pytest.mark.asyncio
    async def test_sanctions_fallback(self, hub):
        """Hub находит sanctions-коннектор (имя в fallback chain: live_sanctions)."""
        # Fallback chain: ["live_sanctions", "local_mirror"]
        # MockSanctionConnector.name = "sanctions" — не совпадает.
        # Регистрируем под именем live_sanctions для теста.
        hub._connectors["live_sanctions"] = MockSanctionConnector()
        result = await hub.fetch("sanctions", {"full_name": "Иванов Иван Иванович"})
        assert result.success
        assert "is_sanctioned" in result.data

    @pytest.mark.asyncio
    async def test_unknown_connector_returns_error(self, hub):
        """Hub возвращает ошибку для неизвестного типа."""
        result = await hub.fetch("nonexistent_type", {})
        assert not result.success
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_health_check(self, hub):
        """Health check всех коннекторов."""
        health = await hub.health_check()
        assert len(health) >= 5
        assert all(health.values())


# ---------------------------------------------------------------------------
# Hub → GraphBuilder: построение графа
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestGraphBuilderPipeline:
    """CompanyGraphBuilder строит корректный граф из данных коннекторов."""

    @pytest.mark.asyncio
    async def test_full_build_company_only(self, builder):
        """Граф для компании без сайта: только company node."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
        )
        assert isinstance(graph, RelationshipGraph)
        assert len(graph.nodes) >= 1

        company_nodes = [n for n in graph.nodes.values() if n.type == "company"]
        assert len(company_nodes) == 1
        assert company_nodes[0].data.get("inn") == "7701234567"

    @pytest.mark.asyncio
    async def test_full_build_with_website(self, builder):
        """Граф с сайтом: company + domain + IP + MX nodes."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        node_types = {n.type for n in graph.nodes.values()}

        assert "company" in node_types
        assert "domain" in node_types
        # DNS возвращает A запись → должен быть IP node
        assert "ip" in node_types

    @pytest.mark.asyncio
    async def test_domain_to_company_edge(self, builder):
        """Связь company → domain (owns) существует."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        company = next(n for n in graph.nodes.values() if n.type == "company")
        domain = next(n for n in graph.nodes.values() if n.type == "domain")

        edges = graph.get_edges_for_node(company.id)
        owns_domain = any(
            e.target == domain.id and e.type == "owns" for e in edges
        )
        assert owns_domain

    @pytest.mark.asyncio
    async def test_domain_to_ip_edge(self, builder):
        """Связь domain → IP (hosted_on) существует."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        domain = next(n for n in graph.nodes.values() if n.type == "domain")
        ip_nodes = [n for n in graph.nodes.values() if n.type == "ip"]
        assert len(ip_nodes) >= 1

        domain_edges = graph.get_edges_for_node(domain.id)
        hosted = [e for e in domain_edges if e.type == "hosted_on"]
        assert len(hosted) >= 1

    @pytest.mark.asyncio
    async def test_vis_js_export(self, builder):
        """Граф экспортируется в vis.js формат."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        vis_data = graph.to_vis_js()

        assert "nodes" in vis_data
        assert "edges" in vis_data
        assert len(vis_data["nodes"]) > 0

        # vis.js node format
        for node in vis_data["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "group" in node

        # vis.js edge format
        for edge in vis_data["edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "arrows" in edge

    @pytest.mark.asyncio
    async def test_neo4j_export(self, builder):
        """Граф экспортируется в Neo4j Cypher запросы."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        queries = graph.to_neo4j_queries()
        assert len(queries) > 0
        assert any("COMPANY" in q for q in queries)

    @pytest.mark.asyncio
    async def test_json_roundtrip(self, builder, tmp_path):
        """Граф сохраняется и загружается из JSON без потерь."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        file_path = builder.save_json(graph, tmp_path / "graph.json")
        loaded = CompanyGraphBuilder.load_json(file_path)

        assert loaded["stats"]["nodes_count"] == len(graph.nodes)
        assert loaded["stats"]["edges_count"] == len(graph.edges)

    @pytest.mark.asyncio
    async def test_stats_consistency(self, builder):
        """Статистика графа соответствует реальному количеству узлов/рёбер."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )
        stats = graph.get_stats()
        assert stats["nodes"] == len(graph.nodes)
        assert stats["edges"] == len(graph.edges)
        assert stats["nodes"] > 0
        assert stats["edges"] > 0


# ---------------------------------------------------------------------------
# API → GraphBuilder → vis.js: полный HTTP цикл
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAPIFullPipeline:
    """Полный цикл: HTTP запрос → API → Hub → Builder → vis.js ответ."""

    @pytest.mark.asyncio
    async def test_get_graph_returns_vis_js(self, api_client):
        """GET /api/v1/graph/{inn} возвращает валидный vis.js JSON."""
        async with api_client as client:
            resp = await client.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        assert resp.status_code == 200
        data = resp.json()

        assert "graph" in data
        assert "stats" in data
        assert data["company_inn"] == "7701234567"
        assert data["stats"]["nodes"] > 0

        # vis.js format
        graph = data["graph"]
        for node in graph["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "group" in node
        for edge in graph["edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "arrows" in edge

    @pytest.mark.asyncio
    async def test_get_graph_stats_match_nodes(self, api_client):
        """Stats.nodes == len(graph.nodes), stats.edges == len(graph.edges)."""
        async with api_client as client:
            resp = await client.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        data = resp.json()
        assert data["stats"]["nodes"] == len(data["graph"]["nodes"])
        assert data["stats"]["edges"] == len(data["graph"]["edges"])

    @pytest.mark.asyncio
    async def test_get_graph_node_types(self, api_client):
        """Граф содержит company, domain, IP узлы при передаче website."""
        async with api_client as client:
            resp = await client.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        data = resp.json()
        node_types = {n["type"] for n in data["graph"]["nodes"]}

        assert "company" in node_types
        assert "domain" in node_types

    @pytest.mark.asyncio
    async def test_get_graph_unknown_inn(self, api_client):
        """Неизвестный ИНН — возвращает company node."""
        async with api_client as client:
            resp = await client.get("/api/v1/graph/9999999999")

        assert resp.status_code == 200
        data = resp.json()
        assert data["company_inn"] == "9999999999"
        assert data["stats"]["nodes"] >= 1

    @pytest.mark.asyncio
    async def test_get_graph_invalid_inn(self, api_client):
        """Невалидный ИНН — 400."""
        async with api_client as client:
            resp = await client.get("/api/v1/graph/abc")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_graph_short_inn(self, api_client):
        """Короткий ИНН — 400."""
        async with api_client as client:
            resp = await client.get("/api/v1/graph/12345")

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_health_endpoint(self, api_client):
        """Health check endpoint работает."""
        async with api_client as client:
            resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Hub → Connector: кэширование
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCaching:
    """Кэширование результатов коннекторов."""

    @pytest.mark.asyncio
    async def test_same_query_returns_cached(self, hub):
        """Повторный запрос возвращает кэшированный результат."""
        params = {"domain": "test-company.ru"}

        result1 = await hub.fetch("whois", params)
        result2 = await hub.fetch("whois", params)

        assert result1.success
        assert result2.success
        assert result1.data == result2.data

    @pytest.mark.asyncio
    async def test_different_queries_different_results(self, hub):
        """Разные запросы возвращают разные результаты."""
        result1 = await hub.fetch("whois", {"domain": "test-company.ru"})
        result2 = await hub.fetch("whois", {"domain": "private-domain.ru"})

        assert result1.success
        assert result2.success
        assert result1.data != result2.data


# ---------------------------------------------------------------------------
# Hub → Connector: error handling
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestErrorHandling:
    """Обработка ошибок в пайплайне."""

    @pytest.mark.asyncio
    async def test_missing_params_returns_error(self, hub):
        """Запрос без параметров возвращает ошибку."""
        result = await hub.fetch("whois", {})
        assert not result.success

    @pytest.mark.asyncio
    async def test_graceful_shodan_skip(self, hub):
        """Shodan пропускается gracefully без API ключа."""
        # MockShodanConnector работает без ключа, но проверяем flow
        result = await hub.fetch("shodan", {"ip": "185.12.34.56"})
        assert result.success
        assert result.data["found"] is True

    @pytest.mark.asyncio
    async def test_shodan_unknown_ip(self, hub):
        """Shodan возвращает found=False для неизвестного IP."""
        result = await hub.fetch("shodan", {"ip": "192.168.1.1"})
        # Mock не знает этот IP → found=False
        assert result.success
        assert result.data.get("found") is False

    @pytest.mark.asyncio
    async def test_whois_unknown_domain(self, hub):
        """WHOIS возвращает дефолтные данные для неизвестного домена."""
        result = await hub.fetch("whois", {"domain": "unknown-domain.xyz"})
        assert result.success
        assert result.data["domain"] == "unknown-domain.xyz"

    @pytest.mark.asyncio
    async def test_dns_unknown_domain(self, hub):
        """DNS возвращает пустые записи для неизвестного домена."""
        result = await hub.fetch("dns", {"domain": "unknown-domain.xyz"})
        assert result.success
        assert result.data["records"]["A"] == []
