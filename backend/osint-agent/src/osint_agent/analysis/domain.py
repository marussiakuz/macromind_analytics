"""Domain Analyzer — объединение WHOIS, DNS и Shodan данных.

Собирает данные из всех коннекторов, анализирует связи между доменами,
формирует Red Flags и готовит контекст для LLM-интерпретации.
"""

import asyncio
from typing import Any

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.models import (
    ConnectorQuery,
    RedFlag,
    RedFlagCategory,
    RedFlagPriority,
)
from osint_agent.utils import get_logger

logger = get_logger(__name__)


class DomainResult:
    """Результат анализа одного домена."""

    def __init__(
        self,
        domain: str,
        whois_data: dict[str, Any] | None = None,
        dns_data: dict[str, Any] | None = None,
        shodan_data: dict[str, Any] | None = None,
        red_flags: list[RedFlag] | None = None,
    ):
        self.domain = domain
        self.whois = whois_data or {}
        self.dns = dns_data or {}
        self.shodan = shodan_data or {}
        self.red_flags = red_flags or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "whois": self.whois,
            "dns": self.dns,
            "shodan": self.shodan,
            "red_flags": [f.model_dump() for f in self.red_flags],
        }


class CompanyDomainAnalysis:
    """Результат анализа всех доменов компании."""

    def __init__(
        self,
        company_name: str,
        inn: str,
        domains: list[DomainResult] | None = None,
        connections: list[dict[str, Any]] | None = None,
        red_flags: list[RedFlag] | None = None,
    ):
        self.company_name = company_name
        self.inn = inn
        self.domains = domains or []
        self.connections = connections or []
        self.red_flags = red_flags or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "inn": self.inn,
            "domains": [d.to_dict() for d in self.domains],
            "connections": self.connections,
            "red_flags": [f.model_dump() for f in self.red_flags],
        }


class DomainAnalyzer:
    """Анализ доменов компании.

    Объединяет данные из:
    - WHOIS (регистрация, владелец)
    - DNS (IP, почтовые серверы, записи)
    - Shodan (инфраструктура, уязвимости, порты)

    Находит:
    - Связи между доменами (общие IP, NS, MX)
    - Red Flags (уязвимости, подозрительные порты, приватная регистрация)
    - Контекст для LLM-интерпретации
    """

    def __init__(self, hub: DataConnectorHub):
        self.hub = hub

    async def analyze_company(
        self,
        company_name: str,
        inn: str,
        website: str | None = None,
    ) -> CompanyDomainAnalysis:
        """Анализ всех доменов компании.

        Args:
            company_name: Название компании
            inn: ИНН компании
            website: Сайт компании (опционально)

        Returns:
            CompanyDomainAnalysis с результатами
        """
        # 1. Найти домены компании
        domains = await self._find_company_domains(company_name, inn, website)

        # 2. Анализировать каждый домен
        domain_results = []
        for domain in domains:
            result = await self._analyze_single_domain(domain)
            domain_results.append(result)

        # 3. Найти связи между доменами
        connections = self._find_domain_connections(domain_results)

        # 4. Собрать все Red Flags
        all_red_flags = []
        for result in domain_results:
            all_red_flags.extend(result.red_flags)

        return CompanyDomainAnalysis(
            company_name=company_name,
            inn=inn,
            domains=domain_results,
            connections=connections,
            red_flags=all_red_flags,
        )

    async def _find_company_domains(
        self,
        company_name: str,
        inn: str,
        website: str | None = None,
    ) -> list[str]:
        """Найти домены компании."""
        domains = set()

        # Добавляем сайт если указан
        if website:
            # Извлекаем домен из URL
            domain = website.replace("https://", "").replace("http://", "")
            domain = domain.split("/")[0]
            domain = domain.replace("www.", "")
            domains.add(domain)

        # TODO: Поиск через WHOIS (по организации)
        # TODO: Поиск через Certificate Transparency

        return list(domains)

    async def _analyze_single_domain(self, domain: str) -> DomainResult:
        """Анализ одного домена."""
        red_flags = []

        # 1. WHOIS данные
        whois_result = await self.hub.fetch("whois", {"domain": domain})
        whois_data = whois_result.data if whois_result.success else {}

        # 2. DNS записи
        dns_result = await self.hub.fetch("dns", {"domain": domain})
        dns_data = dns_result.data if dns_result.success else {}

        # 3. Shodan данные (по IP из DNS)
        shodan_data = {}
        if dns_data and dns_data.get("records", {}).get("A"):
            ip = dns_data["records"]["A"][0]
            shodan_result = await self.hub.fetch("shodan", {"ip": ip})
            if shodan_result.success:
                shodan_data = shodan_result.data

        # 4. Анализ Red Flags
        red_flags.extend(self._analyze_whois_flags(whois_data))
        red_flags.extend(self._analyze_dns_flags(dns_data))
        red_flags.extend(self._analyze_shodan_flags(shodan_data))

        return DomainResult(
            domain=domain,
            whois_data=whois_data,
            dns_data=dns_data,
            shodan_data=shodan_data,
            red_flags=red_flags,
        )

    def _analyze_whois_flags(self, whois_data: dict[str, Any]) -> list[RedFlag]:
        """Анализ WHOIS данных для Red Flags."""
        red_flags = []

        if not whois_data:
            return red_flags

        # Приватная регистрация
        if whois_data.get("is_private_registration"):
            red_flags.append(RedFlag(
                id="DOMAIN_PRIVATE_REGISTRATION",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.LEGAL,
                description="Используется приватная регистрация домена",
                block="D",
                evidence={"domain": whois_data.get("domain")},
                source_ref="WHOIS",
            ))

        # Недавно зарегистрированный
        creation_date = whois_data.get("creation_date")
        if creation_date:
            try:
                from datetime import datetime
                created = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
                age_days = (datetime.utcnow() - created.replace(tzinfo=None)).days

                if age_days < 365:
                    red_flags.append(RedFlag(
                        id="DOMAIN_RECENTLY_REGISTERED",
                        priority=RedFlagPriority.MEDIUM,
                        category=RedFlagCategory.LEGAL,
                        description=f"Домен зарегистрирован менее 1 года назад ({age_days} дней)",
                        block="D",
                        evidence={"creation_date": creation_date, "age_days": age_days},
                        source_ref="WHOIS",
                    ))
            except (ValueError, TypeError):
                pass

        # Срок действия истекает
        expiration_date = whois_data.get("expiration_date")
        if expiration_date:
            try:
                from datetime import datetime
                expires = datetime.fromisoformat(expiration_date.replace("Z", "+00:00"))
                days_left = (expires.replace(tzinfo=None) - datetime.utcnow()).days

                if days_left < 30:
                    red_flags.append(RedFlag(
                        id="DOMAIN_EXPIRING_SOON",
                        priority=RedFlagPriority.MEDIUM,
                        category=RedFlagCategory.LEGAL,
                        description=f"Срок действия домена истекает через {days_left} дней",
                        block="D",
                        evidence={"expiration_date": expiration_date, "days_left": days_left},
                        source_ref="WHOIS",
                    ))
            except (ValueError, TypeError):
                pass

        return red_flags

    def _analyze_dns_flags(self, dns_data: dict[str, Any]) -> list[RedFlag]:
        """Анализ DNS данных для Red Flags."""
        red_flags = []

        if not dns_data:
            return red_flags

        analysis = dns_data.get("analysis", {})

        # Нет SPF
        if not analysis.get("has_spf"):
            red_flags.append(RedFlag(
                id="DNS_NO_SPF",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.TECH,
                description="Домен не настроил SPF запись (уязвим для спуфинга)",
                block="D",
                evidence={"domain": dns_data.get("domain")},
                source_ref="DNS",
            ))

        # Нет DMARC
        has_dmarc = False
        for txt in dns_data.get("records", {}).get("TXT", []):
            if "v=DMARC1" in txt:
                has_dmarc = True
                break

        if not has_dmarc:
            red_flags.append(RedFlag(
                id="DNS_NO_DMARC",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.TECH,
                description="Домен не настроил DMARC запись",
                block="D",
                evidence={"domain": dns_data.get("domain")},
                source_ref="DNS",
            ))

        return red_flags

    def _analyze_shodan_flags(self, shodan_data: dict[str, Any]) -> list[RedFlag]:
        """Анализ Shodan данных для Red Flags."""
        red_flags = []

        if not shodan_data or not shodan_data.get("found"):
            return red_flags

        # Уязвимости
        vulns = shodan_data.get("vulns", [])
        if vulns:
            red_flags.append(RedFlag(
                id="SHODAN_VULNS_FOUND",
                priority=RedFlagPriority.HIGH,
                category=RedFlagCategory.TECH,
                description=f"Обнаружены уязвимости на сервере: {', '.join(vulns[:5])}",
                block="D",
                evidence={
                    "ip": shodan_data.get("ip"),
                    "vulns": vulns,
                    "vulns_count": len(vulns),
                },
                source_ref="Shodan",
            ))

        # Много портов
        ports = shodan_data.get("ports", [])
        if len(ports) > 20:
            red_flags.append(RedFlag(
                id="SHODAN_MANY_PORTS",
                priority=RedFlagPriority.MEDIUM,
                category=RedFlagCategory.TECH,
                description=f"Много открытых портов ({len(ports)}) — возможен плохой контроль доступа",
                block="D",
                evidence={
                    "ip": shodan_data.get("ip"),
                    "ports": ports,
                    "ports_count": len(ports),
                },
                source_ref="Shodan",
            ))

        # Подозрительные порты
        suspicious_ports = {
            21: "FTP (незашифрованный)",
            23: "Telnet (незашифрованный)",
            25: "SMTP (может быть open relay)",
            3389: "RDP (часто атакуется)",
            5900: "VNC (часто атакуется)",
            6379: "Redis (часто открыт без аутентификации)",
            27017: "MongoDB (часто открыт без аутентификации)",
        }

        for port in ports:
            if port in suspicious_ports:
                red_flags.append(RedFlag(
                    id=f"SHODAN_SUSPICIOUS_PORT_{port}",
                    priority=RedFlagPriority.MEDIUM,
                    category=RedFlagCategory.TECH,
                    description=f"Открыт подозрительный порт {port} ({suspicious_ports[port]})",
                    block="D",
                    evidence={
                        "ip": shodan_data.get("ip"),
                        "port": port,
                        "service": suspicious_ports[port],
                    },
                    source_ref="Shodan",
                ))

        return red_flags

    def _find_domain_connections(
        self,
        domain_results: list[DomainResult],
    ) -> list[dict[str, Any]]:
        """Найти связи между доменами."""
        connections = []

        # Группируем по IP
        ip_to_domains: dict[str, list[str]] = {}
        for result in domain_results:
            a_records = result.dns.get("records", {}).get("A", [])
            for ip in a_records:
                if ip not in ip_to_domains:
                    ip_to_domains[ip] = []
                ip_to_domains[ip].append(result.domain)

        # Находим домены на одном IP
        for ip, domains in ip_to_domains.items():
            if len(domains) > 1:
                for i, domain1 in enumerate(domains):
                    for domain2 in domains[i + 1:]:
                        connections.append({
                            "from": domain1,
                            "to": domain2,
                            "type": "same_ip",
                            "value": ip,
                        })

        # Группируем по NS
        ns_to_domains: dict[str, list[str]] = {}
        for result in domain_results:
            ns_records = result.dns.get("records", {}).get("NS", [])
            for ns in ns_records:
                ns = ns.rstrip(".")
                if ns not in ns_to_domains:
                    ns_to_domains[ns] = []
                ns_to_domains[ns].append(result.domain)

        # Находим домены с одним NS
        for ns, domains in ns_to_domains.items():
            if len(domains) > 1:
                for i, domain1 in enumerate(domains):
                    for domain2 in domains[i + 1:]:
                        connections.append({
                            "from": domain1,
                            "to": domain2,
                            "type": "same_nameserver",
                            "value": ns,
                        })

        # Группируем по MX
        mx_to_domains: dict[str, list[str]] = {}
        for result in domain_results:
            mx_records = result.dns.get("records", {}).get("MX", [])
            for mx in mx_records:
                parts = mx.split()
                if len(parts) >= 2:
                    mx_domain = parts[1].rstrip(".")
                    if mx_domain not in mx_to_domains:
                        mx_to_domains[mx_domain] = []
                    mx_to_domains[mx_domain].append(result.domain)

        # Находим домены с одним MX
        for mx, domains in mx_to_domains.items():
            if len(domains) > 1:
                for i, domain1 in enumerate(domains):
                    for domain2 in domains[i + 1:]:
                        connections.append({
                            "from": domain1,
                            "to": domain2,
                            "type": "same_mail_server",
                            "value": mx,
                        })

        return connections

    def prepare_llm_context(self, analysis: CompanyDomainAnalysis) -> str:
        """Подготовить контекст для LLM-интерпретации.

        Args:
            analysis: Результат анализа доменов

        Returns:
            Структурированный текст для LLM
        """
        lines = [
            f"Компания: {analysis.company_name}",
            f"ИНН: {analysis.inn}",
            "",
            "Домены:",
        ]

        for domain_result in analysis.domains:
            lines.append(f"\n--- {domain_result.domain} ---")

            # WHOIS
            if domain_result.whois:
                lines.append(f"  Регистратор: {domain_result.whois.get('registrar', 'Н/Д')}")
                lines.append(f"  Дата регистрации: {domain_result.whois.get('creation_date', 'Н/Д')}")
                lines.append(f"  Приватная регистрация: {'Да' if domain_result.whois.get('is_private_registration') else 'Нет'}")

            # DNS
            if domain_result.dns:
                records = domain_result.dns.get("records", {})
                lines.append(f"  IP-адреса: {', '.join(records.get('A', []))}")
                lines.append(f"  Почтовые серверы: {', '.join(records.get('MX', []))}")
                lines.append(f"  Провайдер почты: {domain_result.dns.get('analysis', {}).get('mail_provider', 'Н/Д')}")

            # Shodan
            if domain_result.shodan and domain_result.shodan.get("found"):
                lines.append(f"  Организация: {domain_result.shodan.get('org', 'Н/Д')}")
                lines.append(f"  Страна: {domain_result.shodan.get('country_name', 'Н/Д')}")
                lines.append(f"  Открытые порты: {domain_result.shodan.get('ports', [])}")
                lines.append(f"  Уязвимости: {domain_result.shodan.get('vulns', [])}")

        # Связи
        if analysis.connections:
            lines.append("\n\nСвязи между доменами:")
            for conn in analysis.connections:
                lines.append(f"  {conn['from']} ↔ {conn['to']} ({conn['type']}: {conn['value']})")

        # Red Flags
        if analysis.red_flags:
            lines.append("\n\nRed Flags:")
            for flag in analysis.red_flags:
                lines.append(f"  [{flag.priority.value}] {flag.description}")

        return "\n".join(lines)
