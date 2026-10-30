"""Tests for Graph API endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.egrul import MockEGRULConnector
from osint_agent.connectors.whois import MockWhoisConnector
from osint_agent.connectors.dns import MockDNSConnector
from osint_agent.connectors.shodan import MockShodanConnector
from osint_agent.connectors.document import MockDocumentConnector
from osint_agent.main import app


def _mock_build_hub():
    """Hub with mock connectors for tests."""
    hub = DataConnectorHub()
    hub.register(MockEGRULConnector())
    hub.register(MockWhoisConnector())
    hub.register(MockDNSConnector())
    hub.register(MockShodanConnector())
    hub.register(MockDocumentConnector())
    return hub


@pytest.fixture
def client():
    """Async test client with mocked hub."""
    transport = ASGITransport(app=app)
    with patch("osint_agent.api.graph._build_hub", _mock_build_hub):
        yield AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.unit
class TestGraphAPI:
    """Tests for GET /api/v1/graph/{inn}."""

    @pytest.mark.asyncio
    async def test_get_graph_known_company(self, client):
        """Test graph for known company (mock EGRUL data)."""
        async with client as c:
            response = await c.get("/api/v1/graph/7701234567")

        assert response.status_code == 200
        data = response.json()

        assert data["company_inn"] == "7701234567"
        assert data["company_name"] != ""
        assert "graph" in data
        assert "stats" in data
        assert data["stats"]["nodes"] >= 1

    @pytest.mark.asyncio
    async def test_get_graph_with_website(self, client):
        """Test graph with website parameter adds domain nodes."""
        async with client as c:
            response = await c.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        assert response.status_code == 200
        data = response.json()

        # Should have more nodes with website
        assert data["stats"]["nodes"] > 1

        # Check vis.js format
        graph = data["graph"]
        assert "nodes" in graph
        assert "edges" in graph

        # Check node types present
        node_types = {n["type"] for n in graph["nodes"]}
        assert "company" in node_types
        assert "domain" in node_types

    @pytest.mark.asyncio
    async def test_get_graph_unknown_company(self, client):
        """Test graph for unknown INN still returns a graph (company node only)."""
        async with client as c:
            response = await c.get("/api/v1/graph/9999999999")

        assert response.status_code == 200
        data = response.json()
        assert data["company_inn"] == "9999999999"
        assert "ИНН 9999999999" in data["company_name"]
        assert data["stats"]["nodes"] >= 1

    @pytest.mark.asyncio
    async def test_get_graph_invalid_inn(self, client):
        """Test graph with invalid INN returns 400."""
        async with client as c:
            response = await c.get("/api/v1/graph/abc")

        assert response.status_code == 400
        assert "ИНН" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_graph_short_inn(self, client):
        """Test graph with short INN returns 400."""
        async with client as c:
            response = await c.get("/api/v1/graph/12345")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_graph_vis_js_format(self, client):
        """Test that graph response matches vis.js format."""
        async with client as c:
            response = await c.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        data = response.json()
        graph = data["graph"]

        # vis.js node format
        for node in graph["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "group" in node

        # vis.js edge format
        for edge in graph["edges"]:
            assert "from" in edge
            assert "to" in edge
            assert "label" in edge
            assert "arrows" in edge

    @pytest.mark.asyncio
    async def test_get_graph_stats(self, client):
        """Test graph stats are consistent."""
        async with client as c:
            response = await c.get(
                "/api/v1/graph/7701234567",
                params={"website": "https://test-company.ru"},
            )

        data = response.json()
        stats = data["stats"]
        graph = data["graph"]

        assert stats["nodes"] == len(graph["nodes"])
        assert stats["edges"] == len(graph["edges"])
        assert stats["nodes"] > 0


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health(self, client):
        async with client as c:
            response = await c.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
