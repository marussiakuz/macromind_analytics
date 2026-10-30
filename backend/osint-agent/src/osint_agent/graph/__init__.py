"""Graph Structure — модели и структура для визуализации связей.

Типы узлов:
- person: Физическое лицо
- company: Компания
- domain: Доменное имя
- ip: IP-адрес
- email: Email-адрес
- phone: Телефон
- organization: Организация (учёба, работа)

Типы связей:
- works_at: Работает в компании
- owns: Владеет (домен, IP, компания)
- hosted_on: Домен размещён на IP
- sends_email: Домен отправляет почту через MX
- friend_of: Связь в соцсетях
- studied_at: Учился в организации
- related_to: Связь через общие данные
"""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Узел графа связей."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str  # "person", "company", "domain", "ip", "email", "phone", "organization"
    label: str
    data: dict[str, Any] = Field(default_factory=dict)
    group: str | None = None

    def get_label(self) -> str:
        """Краткая метка для отображения."""
        if self.type == "person":
            return self.data.get("name", self.label)
        elif self.type == "company":
            return self.data.get("short_name", self.label)
        return self.label

    def get_tooltip(self) -> str:
        """Подсказка при наведении."""
        lines = [f"<b>{self.type.upper()}</b>: {self.label}"]
        for key, value in self.data.items():
            if value and key != "id":
                lines.append(f"{key}: {value}")
        return "<br>".join(lines)

    def to_vis_js(self) -> dict[str, Any]:
        """Экспорт в формат vis.js."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.get_label(),
            "group": self.group or self.type,
            "title": self.get_tooltip(),
        }

    def to_neo4j(self) -> dict[str, Any]:
        """Экспорт в формат Neo4j."""
        return {
            "id": self.id,
            "type": self.type.upper(),
            "label": self.label,
            "properties": self.data,
        }


class GraphEdge(BaseModel):
    """Связь между узлами."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str  # ID источника
    target: str  # ID цели
    type: str  # "works_at", "owns", "hosted_on", etc.
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)

    def to_vis_js(self) -> dict[str, Any]:
        """Экспорт в формат vis.js."""
        return {
            "from": self.source,
            "to": self.target,
            "label": self.label,
            "arrows": "to",
            "title": self.label,
        }

    def to_neo4j(self) -> dict[str, Any]:
        """Экспорт в формат Neo4j."""
        return {
            "source_id": self.source,
            "target_id": self.target,
            "type": self.type.upper(),
            "properties": self.properties,
        }


class RelationshipGraph:
    """Граф связей между сущностями."""

    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []

    def add_node(
        self,
        node_type: str,
        label: str,
        data: dict[str, Any] | None = None,
        group: str | None = None,
    ) -> GraphNode:
        """Добавить узел в граф.

        Если узел с таким типом и label уже существует — обновляет данные.

        Args:
            node_type: Тип узла ("person", "company", "domain", etc.)
            label: Метка узла
            data: Дополнительные данные
            group: Группа для визуализации

        Returns:
            GraphNode
        """
        # Проверяем существование
        existing = self._find_existing_node(node_type, label)
        if existing:
            if data:
                existing.data.update(data)
            return existing

        node = GraphNode(
            type=node_type,
            label=label,
            data=data or {},
            group=group or node_type,
        )
        self.nodes[node.id] = node
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        """Добавить связь между узлами.

        Args:
            source_id: ID узла-источника
            target_id: ID узла-цели
            edge_type: Тип связи ("works_at", "owns", etc.)
            label: Метка связи
            properties: Дополнительные свойства

        Returns:
            GraphEdge
        """
        # Проверяем существование связи
        existing = self._find_existing_edge(source_id, target_id, edge_type)
        if existing:
            if properties:
                existing.properties.update(properties)
            return existing

        edge = GraphEdge(
            source=source_id,
            target=target_id,
            type=edge_type,
            label=label,
            properties=properties or {},
        )
        self.edges.append(edge)
        return edge

    def get_node(self, node_id: str) -> GraphNode | None:
        """Получить узел по ID."""
        return self.nodes.get(node_id)

    def get_edges_for_node(self, node_id: str) -> list[GraphEdge]:
        """Получить все связи узла."""
        return [e for e in self.edges if e.source == node_id or e.target == node_id]

    def get_connected_nodes(self, node_id: str) -> list[GraphNode]:
        """Получить все связанные узлы."""
        connected_ids = set()
        for edge in self.edges:
            if edge.source == node_id:
                connected_ids.add(edge.target)
            elif edge.target == node_id:
                connected_ids.add(edge.source)
        return [self.nodes[nid] for nid in connected_ids if nid in self.nodes]

    def _find_existing_node(self, node_type: str, label: str) -> GraphNode | None:
        """Найти существующий узел по типу и метке."""
        for node in self.nodes.values():
            if node.type == node_type and node.label == label:
                return node
        return None

    def _find_existing_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
    ) -> GraphEdge | None:
        """Найти существующую связь."""
        for edge in self.edges:
            if edge.source == source_id and edge.target == target_id and edge.type == edge_type:
                return edge
        return None

    def to_vis_js(self) -> dict[str, Any]:
        """Экспорт в формат vis.js для визуализации."""
        return {
            "nodes": [node.to_vis_js() for node in self.nodes.values()],
            "edges": [edge.to_vis_js() for edge in self.edges],
        }

    def to_neo4j_queries(self) -> list[str]:
        """Генерация Cypher запросов для Neo4j."""
        queries = []

        # Создание узлов
        for node in self.nodes.values():
            neo4j_node = node.to_neo4j()
            props = ", ".join(
                f"{k}: ${k}" for k in neo4j_node["properties"].keys()
            )
            if props:
                query = f"""
                MERGE (n:{neo4j_node['type']} {{label: $label}})
                SET n += $properties
                """
            else:
                query = f"""
                MERGE (n:{neo4j_node['type']} {{label: $label}})
                """
            queries.append(query)

        # Создание связей
        for edge in self.edges:
            neo4j_edge = edge.to_neo4j()
            props = ", ".join(
                f"{k}: ${k}" for k in neo4j_edge["properties"].keys()
            )
            if props:
                query = f"""
                MATCH (a {{id: $source_id}})
                MATCH (b {{id: $target_id}})
                MERGE (a)-[r:{neo4j_edge['type']}]->(b)
                SET r += $properties
                """
            else:
                query = f"""
                MATCH (a {{id: $source_id}})
                MATCH (b {{id: $target_id}})
                MERGE (a)-[r:{neo4j_edge['type']}]->(b)
                """
            queries.append(query)

        return queries

    def to_dict(self) -> dict[str, Any]:
        """Экспорт в словарь."""
        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "label": node.label,
                    "data": node.data,
                    "group": node.group,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                    "label": edge.label,
                    "properties": edge.properties,
                }
                for edge in self.edges
            ],
            "stats": {
                "nodes_count": len(self.nodes),
                "edges_count": len(self.edges),
            },
        }

    def get_stats(self) -> dict[str, int]:
        """Получить статистику графа."""
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
        }


# Константы для типов узлов
NODE_TYPES = {
    "person": {"color": "#FF6B6B", "shape": "dot"},
    "company": {"color": "#4ECDC4", "shape": "dot"},
    "domain": {"color": "#45B7D1", "shape": "dot"},
    "ip": {"color": "#96CEB4", "shape": "dot"},
    "email": {"color": "#FFEAA7", "shape": "dot"},
    "phone": {"color": "#DDA0DD", "shape": "dot"},
    "organization": {"color": "#A8E6CF", "shape": "dot"},
}

from osint_agent.graph.builder import CompanyGraphBuilder

# Константы для типов связей
EDGE_TYPES = {
    "works_at": {"color": "#666666", "dashes": False},
    "owns": {"color": "#FF6B6B", "dashes": False},
    "hosted_on": {"color": "#45B7D1", "dashes": True},
    "sends_email": {"color": "#FFEAA7", "dashes": True},
    "friend_of": {"color": "#A8E6CF", "dashes": False},
    "studied_at": {"color": "#DDA0DD", "dashes": True},
    "related_to": {"color": "#999999", "dashes": True},
}
