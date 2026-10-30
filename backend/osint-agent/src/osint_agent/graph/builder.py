"""CompanyGraphBuilder — стрит граф связей для компании.

Собирает данные из всех доступных коннекторов и формирует
RelationshipGraph с узлами (company, person, domain, IP, email, phone)
и связями между ними.

Данные хранятся in-memory, экспорт в JSON / vis.js / Neo4j queries.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.graph import RelationshipGraph
from osint_agent.models import ConnectorResult
from osint_agent.utils import get_logger

logger = get_logger(__name__)


class CompanyGraphBuilder:
    """Строит граф связей компании из данных коннекторов.

    Источники данных:
    - ЕГРЮЛ (Block A): компания, директор, учредители
    - WHOIS (Block B): домены
    - DNS (Block C): IP-адреса, MX-серверы
    - Shodan (Block D): обогащение IP
    - Document (Block E): авторы, email, телефоны из метаданных
    """

    def __init__(self, hub: DataConnectorHub):
        self.hub = hub

    async def build(
        self,
        company_name: str,
        inn: str,
        website: str | None = None,
        documents: list[str] | None = None,
        company_result: ConnectorResult | None = None,
    ) -> RelationshipGraph:
        """Построить граф связей для компании.

        Args:
            company_name: Название компании
            inn: ИНН компании
            website: Сайт компании (опционально)
            documents: Пути к документам для анализа (опционально)

        Returns:
            RelationshipGraph с узлами и связями
        """
        graph = RelationshipGraph()

        # 1. ЕГРЮЛ — компания и персоны
        company_node = await self._add_company_data(graph, company_name, inn, company_result)

        # 2. WHOIS + DNS + Shodan — домены и инфраструктура
        if website:
            await self._add_domain_data(graph, company_node, website, inn)

        # 3. Документы — авторы, email, телефоны
        if documents:
            await self._add_document_data(graph, company_node, documents)

        logger.info(
            "graph_built",
            company=company_name,
            inn=inn,
            nodes=len(graph.nodes),
            edges=len(graph.edges),
        )

        return graph

    async def _add_company_data(
        self,
        graph: RelationshipGraph,
        company_name: str,
        inn: str,
        company_result: ConnectorResult | None = None,
    ):
        """Добавить данные компании из ЕГРЮЛ."""
        # Company node
        company_node = graph.add_node(
            node_type="company",
            label=company_name,
            data={"inn": inn},
        )

        # Fetch EGRUL data
        egrul_result = (company_result if company_result is not None else
                        await self.hub.fetch("company_legal", {"inn": inn}))

        if egrul_result.success and egrul_result.data:
            data = egrul_result.data

            # Enrich company node
            company_node.data.update({
                "ogrn": data.get("ogrn", ""),
                "full_name": data.get("full_name", ""),
                "legal_form": data.get("legal_form", ""),
                "address": data.get("address", ""),
                "status": data.get("status", ""),
                "registration_date": data.get("registration_date", ""),
                "okved_main": data.get("okved_main", ""),
            })

            # Director (from Block C — management)
            # EGRUL data may contain director info in extended fields
            director_name = data.get("director")
            if director_name:
                director_node = graph.add_node(
                    node_type="person",
                    label=director_name,
                    data={"role": "director", "company_inn": inn},
                )
                graph.add_edge(
                    source_id=director_node.id,
                    target_id=company_node.id,
                    edge_type="works_at",
                    label="Директор",
                    properties={"position": "Генеральный директор"},
                )

            # Shareholders (from Block B)
            shareholders = data.get("shareholders", [])
            for sh in shareholders:
                sh_name = sh.get("name", "")
                sh_type = sh.get("type", "person")
                sh_inn = sh.get("inn")

                if sh_type == "person":
                    sh_node = graph.add_node(
                        node_type="person",
                        label=sh_name,
                        data={"role": "shareholder"},
                    )
                else:
                    sh_node = graph.add_node(
                        node_type="company",
                        label=sh_name,
                        data={"inn": sh_inn or ""},
                    )

                graph.add_edge(
                    source_id=sh_node.id,
                    target_id=company_node.id,
                    edge_type="owns",
                    label=f"Учредитель ({sh.get('share_percent', 0)}%)",
                    properties={"share_percent": sh.get("share_percent", 0)},
                )

        return company_node

    async def _add_domain_data(
        self,
        graph: RelationshipGraph,
        company_node,
        website: str,
        inn: str,
    ):
        """Добавить данные домена: WHOIS → DNS → Shodan."""
        # Extract domain from URL
        domain = website.replace("https://", "").replace("http://", "")
        domain = domain.split("/")[0].replace("www.", "")

        # Domain node
        domain_node = graph.add_node(
            node_type="domain",
            label=domain,
            data={"website": website},
        )

        # Company owns domain
        graph.add_edge(
            source_id=company_node.id,
            target_id=domain_node.id,
            edge_type="owns",
            label="Владеет сайтом",
        )

        # WHOIS
        whois_result = await self.hub.fetch("whois", {"domain": domain})
        if whois_result.success and whois_result.data:
            whois_data = whois_result.data
            domain_node.data.update({
                "registrar": whois_data.get("registrar", ""),
                "creation_date": whois_data.get("creation_date", ""),
                "expiration_date": whois_data.get("expiration_date", ""),
                "is_private_registration": whois_data.get("is_private_registration", False),
            })

        # DNS
        dns_result = await self.hub.fetch("dns", {"domain": domain})
        if dns_result.success and dns_result.data:
            dns_data = dns_result.data
            records = dns_data.get("records", {})

            # IP addresses
            for ip in records.get("A", []):
                ip_node = graph.add_node(
                    node_type="ip",
                    label=ip,
                    data={},
                )
                graph.add_edge(
                    source_id=domain_node.id,
                    target_id=ip_node.id,
                    edge_type="hosted_on",
                    label="Размещён на",
                )

                # Shodan enrichment for each IP
                await self._enrich_ip_from_shodan(graph, ip_node)

            # MX records → email servers
            for mx in records.get("MX", []):
                parts = mx.split()
                mx_host = parts[1].rstrip(".") if len(parts) >= 2 else mx
                email_node = graph.add_node(
                    node_type="organization",
                    label=mx_host,
                    data={"type": "mail_server"},
                )
                graph.add_edge(
                    source_id=domain_node.id,
                    target_id=email_node.id,
                    edge_type="sends_email",
                    label="Почта через",
                )

    async def _enrich_ip_from_shodan(
        self,
        graph: RelationshipGraph,
        ip_node,
    ):
        """Обогатить IP-узел данными из Shodan."""
        shodan_result = await self.hub.fetch("shodan", {"ip": ip_node.label})

        if shodan_result.success and shodan_result.data:
            data = shodan_result.data
            if data.get("found"):
                ip_node.data.update({
                    "org": data.get("org", ""),
                    "country": data.get("country_name", ""),
                    "city": data.get("city", ""),
                    "os": data.get("os", ""),
                    "ports": data.get("ports", []),
                    "vulns": data.get("vulns", []),
                    "hostnames": data.get("hostnames", []),
                })

    async def _add_document_data(
        self,
        graph: RelationshipGraph,
        company_node,
        documents: list[str],
    ):
        """Добавить данные из метаданных документов."""
        for doc_path in documents:
            doc_result = await self.hub.fetch("document", {"file_path": doc_path, "extract_text": True})

            if not doc_result.success or not doc_result.data:
                continue

            data = doc_result.data

            # Support both flat and nested structures
            metadata = data.get("metadata", data)
            entities = data.get("entities", {})
            emails = entities.get("emails", metadata.get("emails_found", []))
            phones = entities.get("phones", metadata.get("phones_found", []))

            # Document author
            author = metadata.get("author")
            if author:
                author_node = graph.add_node(
                    node_type="person",
                    label=author,
                    data={"role": "document_author", "source_doc": doc_path},
                )
                graph.add_edge(
                    source_id=author_node.id,
                    target_id=company_node.id,
                    edge_type="related_to",
                    label="Автор документа",
                    properties={"document": doc_path},
                )

            # Emails found in document
            for email in emails:
                email_node = graph.add_node(
                    node_type="email",
                    label=email,
                    data={"source_doc": doc_path},
                )
                graph.add_edge(
                    source_id=company_node.id,
                    target_id=email_node.id,
                    edge_type="owns",
                    label="Использует email",
                    properties={"document": doc_path},
                )

            # Phones found in document
            for phone in phones:
                phone_node = graph.add_node(
                    node_type="phone",
                    label=phone,
                    data={"source_doc": doc_path},
                )
                graph.add_edge(
                    source_id=company_node.id,
                    target_id=phone_node.id,
                    edge_type="owns",
                    label="Телефон",
                    properties={"document": doc_path},
                )

    def save_json(self, graph: RelationshipGraph, path: str | Path) -> Path:
        """Сохранить граф в JSON файл.

        Args:
            graph: RelationshipGraph для сохранения
            path: Путь к файлу

        Returns:
            Path к сохранённому файлу
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = graph.to_dict()
        data["exported_at"] = datetime.utcnow().isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("graph_saved", path=str(path), nodes=data["stats"]["nodes_count"])
        return path

    @staticmethod
    def load_json(path: str | Path) -> dict[str, Any]:
        """Загрузить граф из JSON файла.

        Args:
            path: Путь к JSON файлу

        Returns:
            Словарь с данными графа
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
