"""Tests for Graph Structure."""

import pytest

from osint_agent.graph import (
    GraphNode,
    GraphEdge,
    RelationshipGraph,
    NODE_TYPES,
    EDGE_TYPES,
)


@pytest.mark.unit
class TestGraphNode:
    """Tests for GraphNode."""

    def test_creation(self):
        """Test GraphNode creation."""
        node = GraphNode(
            type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович", "inn": "1234567890"},
        )

        assert node.type == "person"
        assert node.label == "Иванов Иван"
        assert node.data["name"] == "Иванов Иван Иванович"
        assert node.id is not None

    def test_get_label_person(self):
        """Test get_label for person."""
        node = GraphNode(
            type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович"},
        )

        assert node.get_label() == "Иванов Иван Иванович"

    def test_get_label_company(self):
        """Test get_label for company."""
        node = GraphNode(
            type="company",
            label='ООО "Тест"',
            data={"short_name": "Тест"},
        )

        assert node.get_label() == "Тест"

    def test_get_label_default(self):
        """Test get_label default."""
        node = GraphNode(
            type="domain",
            label="example.com",
        )

        assert node.get_label() == "example.com"

    def test_get_tooltip(self):
        """Test get_tooltip."""
        node = GraphNode(
            type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович", "city": "Москва"},
        )

        tooltip = node.get_tooltip()

        assert "PERSON" in tooltip
        assert "Иванов Иван" in tooltip
        assert "city" in tooltip
        assert "Москва" in tooltip

    def test_to_vis_js(self):
        """Test vis.js export."""
        node = GraphNode(
            type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович"},
            group="employees",
        )

        vis_data = node.to_vis_js()

        assert vis_data["id"] == node.id
        assert vis_data["label"] == "Иванов Иван Иванович"
        assert vis_data["group"] == "employees"
        assert "title" in vis_data

    def test_to_neo4j(self):
        """Test Neo4j export."""
        node = GraphNode(
            type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович", "inn": "1234567890"},
        )

        neo4j_data = node.to_neo4j()

        assert neo4j_data["id"] == node.id
        assert neo4j_data["type"] == "PERSON"
        assert neo4j_data["label"] == "Иванов Иван"
        assert neo4j_data["properties"]["name"] == "Иванов Иван Иванович"


@pytest.mark.unit
class TestGraphEdge:
    """Tests for GraphEdge."""

    def test_creation(self):
        """Test GraphEdge creation."""
        edge = GraphEdge(
            source="node1",
            target="node2",
            type="works_at",
            label="Работает в",
        )

        assert edge.source == "node1"
        assert edge.target == "node2"
        assert edge.type == "works_at"
        assert edge.id is not None

    def test_to_vis_js(self):
        """Test vis.js export."""
        edge = GraphEdge(
            source="node1",
            target="node2",
            type="works_at",
            label="Работает в",
        )

        vis_data = edge.to_vis_js()

        assert vis_data["from"] == "node1"
        assert vis_data["to"] == "node2"
        assert vis_data["label"] == "Работает в"
        assert vis_data["arrows"] == "to"

    def test_to_neo4j(self):
        """Test Neo4j export."""
        edge = GraphEdge(
            source="node1",
            target="node2",
            type="works_at",
            label="Работает в",
            properties={"since": "2020-01-01"},
        )

        neo4j_data = edge.to_neo4j()

        assert neo4j_data["source_id"] == "node1"
        assert neo4j_data["target_id"] == "node2"
        assert neo4j_data["type"] == "WORKS_AT"
        assert neo4j_data["properties"]["since"] == "2020-01-01"


@pytest.mark.unit
class TestRelationshipGraph:
    """Tests for RelationshipGraph."""

    @pytest.fixture
    def graph(self):
        return RelationshipGraph()

    def test_add_node(self, graph):
        """Test adding node."""
        node = graph.add_node(
            node_type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович"},
        )

        assert node.type == "person"
        assert node.label == "Иванов Иван"
        assert len(graph.nodes) == 1

    def test_add_node_duplicate(self, graph):
        """Test adding duplicate node updates data."""
        node1 = graph.add_node(
            node_type="person",
            label="Иванов Иван",
            data={"name": "Иванов Иван Иванович"},
        )
        node2 = graph.add_node(
            node_type="person",
            label="Иванов Иван",
            data={"city": "Москва"},
        )

        assert node1.id == node2.id
        assert node2.data["name"] == "Иванов Иван Иванович"
        assert node2.data["city"] == "Москва"
        assert len(graph.nodes) == 1

    def test_add_edge(self, graph):
        """Test adding edge."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')

        edge = graph.add_edge(
            source_id=node1.id,
            target_id=node2.id,
            edge_type="works_at",
            label="Работает в",
        )

        assert edge.source == node1.id
        assert edge.target == node2.id
        assert len(graph.edges) == 1

    def test_add_edge_duplicate(self, graph):
        """Test adding duplicate edge updates properties."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')

        edge1 = graph.add_edge(
            source_id=node1.id,
            target_id=node2.id,
            edge_type="works_at",
            label="Работает в",
            properties={"position": "CEO"},
        )
        edge2 = graph.add_edge(
            source_id=node1.id,
            target_id=node2.id,
            edge_type="works_at",
            label="Работает в",
            properties={"since": "2020-01-01"},
        )

        assert edge1.id == edge2.id
        assert edge2.properties["position"] == "CEO"
        assert edge2.properties["since"] == "2020-01-01"
        assert len(graph.edges) == 1

    def test_get_node(self, graph):
        """Test getting node by ID."""
        node = graph.add_node("person", "Иванов")

        found = graph.get_node(node.id)

        assert found is not None
        assert found.id == node.id

    def test_get_node_not_found(self, graph):
        """Test getting non-existent node."""
        found = graph.get_node("nonexistent")

        assert found is None

    def test_get_edges_for_node(self, graph):
        """Test getting edges for node."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')
        node3 = graph.add_node("company", 'ООО "Другая"')

        graph.add_edge(node1.id, node2.id, "works_at", "Работает")
        graph.add_edge(node1.id, node3.id, "works_at", "Работает")
        graph.add_edge(node2.id, node3.id, "related_to", "Связана")

        edges = graph.get_edges_for_node(node1.id)

        assert len(edges) == 2

    def test_get_connected_nodes(self, graph):
        """Test getting connected nodes."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')
        node3 = graph.add_node("company", 'ООО "Другая"')

        graph.add_edge(node1.id, node2.id, "works_at", "Работает")
        graph.add_edge(node1.id, node3.id, "works_at", "Работает")

        connected = graph.get_connected_nodes(node1.id)

        assert len(connected) == 2
        connected_labels = [n.label for n in connected]
        assert 'ООО "Тест"' in connected_labels
        assert 'ООО "Другая"' in connected_labels

    def test_to_vis_js(self, graph):
        """Test vis.js export."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')
        graph.add_edge(node1.id, node2.id, "works_at", "Работает")

        vis_data = graph.to_vis_js()

        assert len(vis_data["nodes"]) == 2
        assert len(vis_data["edges"]) == 1
        assert vis_data["nodes"][0]["type"] == "person"
        assert vis_data["edges"][0]["from"] == node1.id

    def test_to_neo4j_queries(self, graph):
        """Test Neo4j query generation."""
        node1 = graph.add_node("person", "Иванов", data={"name": "Иванов Иван"})
        node2 = graph.add_node("company", 'ООО "Тест"')
        graph.add_edge(node1.id, node2.id, "works_at", "Работает")

        queries = graph.to_neo4j_queries()

        assert len(queries) == 3  # 2 nodes + 1 edge
        assert "PERSON" in queries[0]
        assert "COMPANY" in queries[1]
        assert "WORKS_AT" in queries[2]

    def test_to_dict(self, graph):
        """Test dictionary export."""
        node1 = graph.add_node("person", "Иванов")
        node2 = graph.add_node("company", 'ООО "Тест"')
        graph.add_edge(node1.id, node2.id, "works_at", "Работает")

        data = graph.to_dict()

        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["stats"]["nodes_count"] == 2
        assert data["stats"]["edges_count"] == 1

    def test_get_stats(self, graph):
        """Test stats."""
        graph.add_node("person", "Иванов")
        graph.add_node("company", 'ООО "Тест"')
        graph.add_node("domain", "example.com")

        stats = graph.get_stats()

        assert stats["nodes"] == 3
        assert stats["edges"] == 0

    def test_complex_graph(self, graph):
        """Test complex graph construction."""
        # Добавляем узлы
        person = graph.add_node("person", "Иванов Иван", data={"name": "Иванов Иван Иванович"})
        company1 = graph.add_node("company", 'ООО "Рога"', data={"inn": "7701234567"})
        company2 = graph.add_node("company", 'ООО "Копыта"', data={"inn": "7701234568"})
        domain = graph.add_node("domain", "roga.ru")
        ip = graph.add_node("ip", "1.2.3.4")
        email = graph.add_node("email", "ivan@roga.ru")

        # Добавляем связи
        graph.add_edge(person.id, company1.id, "owns", "Владеет", {"share": "50%"})
        graph.add_edge(person.id, company2.id, "owns", "Владеет", {"share": "100%"})
        graph.add_edge(company1.id, domain.id, "owns", "Владеет")
        graph.add_edge(domain.id, ip.id, "hosted_on", "Размещён на")
        graph.add_edge(company1.id, email.id, "owns", "Использует")

        # Проверяем
        assert len(graph.nodes) == 6
        assert len(graph.edges) == 5

        # Проверяем связи человека
        person_edges = graph.get_edges_for_node(person.id)
        assert len(person_edges) == 2

        # Проверяем связанные узлы компании
        company1_connected = graph.get_connected_nodes(company1.id)
        assert len(company1_connected) == 3  # person, domain, email

        # Проверяем экспорт
        vis_data = graph.to_vis_js()
        assert len(vis_data["nodes"]) == 6
        assert len(vis_data["edges"]) == 5


@pytest.mark.unit
class TestConstants:
    """Tests for constants."""

    def test_node_types(self):
        """Test NODE_TYPES contains all types."""
        expected_types = ["person", "company", "domain", "ip", "email", "phone", "organization"]
        for t in expected_types:
            assert t in NODE_TYPES
            assert "color" in NODE_TYPES[t]
            assert "shape" in NODE_TYPES[t]

    def test_edge_types(self):
        """Test EDGE_TYPES contains all types."""
        expected_types = ["works_at", "owns", "hosted_on", "sends_email", "friend_of", "studied_at", "related_to"]
        for t in expected_types:
            assert t in EDGE_TYPES
            assert "color" in EDGE_TYPES[t]
            assert "dashes" in EDGE_TYPES[t]
