"""Tests for CompanyGraphBuilder."""

import json
import pytest
from pathlib import Path

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.mock import (
    MockSanctionConnector,
    MockNewsConnector,
    MockPEPConnector,
    MockSocialConnector,
)
from osint_agent.connectors.egrul import MockEGRULConnector
from osint_agent.connectors.whois import MockWhoisConnector
from osint_agent.connectors.dns import MockDNSConnector
from osint_agent.connectors.shodan import MockShodanConnector
from osint_agent.connectors.document import MockDocumentConnector
from osint_agent.graph import RelationshipGraph
from osint_agent.graph.builder import CompanyGraphBuilder


@pytest.fixture
def hub():
    """DataConnectorHub with all mock connectors."""
    h = DataConnectorHub()
    h.register(MockEGRULConnector())
    h.register(MockWhoisConnector())
    h.register(MockDNSConnector())
    h.register(MockShodanConnector())
    h.register(MockDocumentConnector())
    h.register(MockSanctionConnector())
    h.register(MockNewsConnector())
    h.register(MockPEPConnector())
    h.register(MockSocialConnector())
    return h


@pytest.fixture
def builder(hub):
    return CompanyGraphBuilder(hub)


@pytest.mark.unit
class TestCompanyGraphBuilder:
    """Tests for CompanyGraphBuilder."""

    @pytest.mark.asyncio
    async def test_build_basic(self, builder):
        """Test basic graph build with company data only."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
        )

        assert isinstance(graph, RelationshipGraph)
        assert len(graph.nodes) >= 1  # At least company node

        # Check company node exists
        company_nodes = [n for n in graph.nodes.values() if n.type == "company"]
        assert len(company_nodes) == 1
        assert company_nodes[0].data.get("inn") == "7701234567"

    @pytest.mark.asyncio
    async def test_build_with_website(self, builder):
        """Test graph build with website adds domain + IP nodes."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        node_types = {n.type for n in graph.nodes.values()}

        # Should have company + domain + IP nodes
        assert "company" in node_types
        assert "domain" in node_types

        # Check domain node
        domain_nodes = [n for n in graph.nodes.values() if n.type == "domain"]
        assert len(domain_nodes) == 1
        assert "test-company.ru" in domain_nodes[0].label

    @pytest.mark.asyncio
    async def test_build_domain_connections(self, builder):
        """Test that domain -> company ownership edge exists."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        # Find company and domain nodes
        company_node = None
        domain_node = None
        for node in graph.nodes.values():
            if node.type == "company":
                company_node = node
            elif node.type == "domain":
                domain_node = node

        assert company_node is not None
        assert domain_node is not None

        # Check ownership edge
        edges = graph.get_edges_for_node(company_node.id)
        owns_domain = any(
            e.target == domain_node.id and e.type == "owns"
            for e in edges
        )
        assert owns_domain

    @pytest.mark.asyncio
    async def test_build_ip_nodes(self, builder):
        """Test that DNS A records create IP nodes with hosted_on edges."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        ip_nodes = [n for n in graph.nodes.values() if n.type == "ip"]
        assert len(ip_nodes) >= 1

        # Check hosted_on edges
        domain_node = next(n for n in graph.nodes.values() if n.type == "domain")
        domain_edges = graph.get_edges_for_node(domain_node.id)
        hosted_edges = [e for e in domain_edges if e.type == "hosted_on"]
        assert len(hosted_edges) >= 1

    @pytest.mark.asyncio
    async def test_build_no_website(self, builder):
        """Test graph without website has no domain/IP nodes."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
        )

        node_types = {n.type for n in graph.nodes.values()}
        assert "domain" not in node_types
        assert "ip" not in node_types

    @pytest.mark.asyncio
    async def test_build_stats(self, builder):
        """Test graph stats are correct."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        stats = graph.get_stats()
        assert stats["nodes"] > 0
        assert stats["edges"] > 0
        assert stats["nodes"] == len(graph.nodes)
        assert stats["edges"] == len(graph.edges)

    @pytest.mark.asyncio
    async def test_build_vis_js_export(self, builder):
        """Test vis.js export from built graph."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        vis_data = graph.to_vis_js()
        assert "nodes" in vis_data
        assert "edges" in vis_data
        assert len(vis_data["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_build_neo4j_export(self, builder):
        """Test Neo4j query generation from built graph."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        queries = graph.to_neo4j_queries()
        assert len(queries) > 0
        # Should contain COMPANY label
        assert any("COMPANY" in q for q in queries)


@pytest.mark.unit
class TestGraphBuilderJSON:
    """Tests for JSON export/import."""

    @pytest.mark.asyncio
    async def test_save_json(self, builder, tmp_path):
        """Test saving graph to JSON file."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru",
        )

        file_path = builder.save_json(graph, tmp_path / "graph.json")
        assert file_path.exists()

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert "exported_at" in data
        assert data["stats"]["nodes_count"] > 0

    @pytest.mark.asyncio
    async def test_load_json(self, builder, tmp_path):
        """Test loading graph from JSON file."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
        )

        file_path = builder.save_json(graph, tmp_path / "graph.json")
        loaded = CompanyGraphBuilder.load_json(file_path)

        assert loaded["stats"]["nodes_count"] == len(graph.nodes)
        assert len(loaded["nodes"]) == len(graph.nodes)

    @pytest.mark.asyncio
    async def test_save_json_creates_dirs(self, builder, tmp_path):
        """Test that save_json creates parent directories."""
        nested_path = tmp_path / "a" / "b" / "c" / "graph.json"
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
        )

        file_path = builder.save_json(graph, nested_path)
        assert file_path.exists()


@pytest.mark.unit
class TestGraphBuilderEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_build_unknown_company(self, builder):
        """Test graph build with unknown INN still creates company node."""
        graph = await builder.build(
            company_name="Неизвестная компания",
            inn="9999999999",
        )

        assert len(graph.nodes) == 1
        company = list(graph.nodes.values())[0]
        assert company.type == "company"
        assert company.label == "Неизвестная компания"

    @pytest.mark.asyncio
    async def test_build_empty_website(self, builder):
        """Test graph build with empty website string."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="",
        )

        node_types = {n.type for n in graph.nodes.values()}
        assert "domain" not in node_types

    @pytest.mark.asyncio
    async def test_build_website_with_path(self, builder):
        """Test that website URL path is stripped to domain."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://test-company.ru/about/team",
        )

        domain_nodes = [n for n in graph.nodes.values() if n.type == "domain"]
        assert len(domain_nodes) == 1
        assert domain_nodes[0].label == "test-company.ru"

    @pytest.mark.asyncio
    async def test_build_website_with_www(self, builder):
        """Test that www. prefix is stripped from domain."""
        graph = await builder.build(
            company_name='ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            inn="7701234567",
            website="https://www.test-company.ru",
        )

        domain_nodes = [n for n in graph.nodes.values() if n.type == "domain"]
        assert len(domain_nodes) == 1
        assert "www." not in domain_nodes[0].label
