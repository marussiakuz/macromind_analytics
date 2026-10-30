"""DNS Connector — получение DNS записей доменов.

Источник: dnspython — стандартная библиотека для DNS запросов.

Получает:
- A/AAAA записи — IP-адреса домена
- MX записи — почтовые серверы
- TXT записи — SPF, DKIM, другие конфигурации
- CNAME записи — псевдонимы доменов
- NS записи — серверы имен
- SOA запись — информация о зоне

ВАЖНО (152-ФЗ):
- DNS записи НЕ содержат персональных данных
- Это техническая информация, не регулируется 152-ФЗ
- Можно свободно собирать и хранить
"""

import asyncio
from typing import Any

import dns.resolver
import dns.reversename

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult
from osint_agent.utils import get_logger

logger = get_logger(__name__)

# Типы DNS записей для анализа
RECORD_TYPES = ["A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA"]


class DNSConnector(BaseConnector):
    """DNS запросы к доменам.

    Получает все основные типы DNS записей:
    - A/AAAA — IP-адреса
    - MX — почтовые серверы
    - TXT — SPF, DKIM, конфигурации
    - CNAME — псевдонимы
    - NS — серверы имен
    - SOA — информация о зоне

    Также выполняет:
    - Обратный DNS поиск (IP → домены)
    - Анализ связей между доменами
    """

    @property
    def name(self) -> str:
        return "dns"

    @property
    def rate_limit(self) -> int:
        return 120  # 2 запроса в секунду

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить DNS записи домена.

        Args:
            query: ConnectorQuery с params:
                - domain: str (доменное имя)
                - record_types: list[str] (опционально, типы записей)

        Returns:
            ConnectorResult с DNS записями
        """
        domain = query.params.get("domain")
        if not domain:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="Domain is required",
            )

        record_types = query.params.get("record_types", RECORD_TYPES)

        try:
            # Получаем DNS записи
            records = {}
            for record_type in record_types:
                records[record_type] = await self._query_dns(domain, record_type)

            # Обратный поиск по IP (если есть A запись)
            reverse_dns = {}
            if records.get("A"):
                for ip in records["A"]:
                    reverse_domains = await self._reverse_dns(ip)
                    if reverse_domains:
                        reverse_dns[ip] = reverse_domains

            # Формируем результат
            result_data = {
                "domain": domain,
                "records": records,
                "reverse_dns": reverse_dns,
                "analysis": self._analyze_records(records),
            }

            return ConnectorResult(
                success=True,
                data=result_data,
                source=self.name,
                confidence=1.0,
            )

        except Exception as e:
            logger.error("dns_error", domain=domain, error=str(e))
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _query_dns(self, domain: str, record_type: str) -> list[str]:
        """DNS запрос определённого типа."""
        import asyncio

        try:
            answers = await asyncio.to_thread(
                dns.resolver.resolve, domain, record_type,
            )
            return [str(rdata) for rdata in answers]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return []
        except Exception as e:
            logger.debug("dns_query_error", domain=domain, type=record_type, error=str(e))
            return []

    async def _reverse_dns(self, ip: str) -> list[str]:
        """Обратный DNS поиск по IP."""
        import asyncio

        try:
            addr = dns.reversename.from_address(ip)
            hostnames = await asyncio.to_thread(
                dns.resolver.resolve, addr, "PTR",
            )
            return [str(h).rstrip(".") for h in hostnames]
        except Exception:
            return []

    def _analyze_records(self, records: dict[str, list[str]]) -> dict[str, Any]:
        """Анализ DNS записей."""
        analysis = {
            "has_ipv4": bool(records.get("A")),
            "has_ipv6": bool(records.get("AAAA")),
            "has_mail": bool(records.get("MX")),
            "has_spf": False,
            "has_dkim": False,
            "mail_provider": None,
            "hosting_provider": None,
        }

        # Анализ TXT записей (SPF, DKIM)
        for txt in records.get("TXT", []):
            if "v=spf1" in txt:
                analysis["has_spf"] = True
            if "v=DKIM1" in txt:
                analysis["has_dkim"] = True

        # Определение почтового провайдера по MX записям
        mx_records = records.get("MX", [])
        if mx_records:
            analysis["mail_provider"] = self._detect_mail_provider(mx_records)

        # Определение хостинг-провайдера по A записи
        a_records = records.get("A", [])
        if a_records:
            analysis["hosting_provider"] = "unknown"  # TODO: определить через Shodan

        return analysis

    def _detect_mail_provider(self, mx_records: list[str]) -> str:
        """Определить почтовый провайдер по MX записям."""
        mx_text = " ".join(mx_records).lower()

        providers = {
            "yandex": ["yandex.net", "yandex.ru", "yandex.com"],
            "google": ["google.com", "googlemail.com", "gmail.com"],
            "mail.ru": ["mail.ru", "bk.ru", "list.ru", "inbox.ru"],
            "outlook": ["outlook.com", "microsoft.com", "office365.com"],
            "zoho": ["zoho.com", "zohomail.com"],
            "mailchimp": ["mailchimp.com"],
            "amazonses": ["amazonses.com", "aws.amazon.com"],
        }

        for provider, domains in providers.items():
            for domain in domains:
                if domain in mx_text:
                    return provider

        return "other"

    async def health_check(self) -> bool:
        """Проверить доступность DNS."""
        try:
            import dns.resolver
            loop = __import__('asyncio').get_running_loop()
            await loop.run_in_executor(None, lambda: dns.resolver.resolve("google.com", "A"))
            return True
        except Exception:
            return False


class MockDNSConnector(BaseConnector):
    """Mock DNS connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "test-company.ru": {
            "domain": "test-company.ru",
            "records": {
                "A": ["185.12.34.56"],
                "AAAA": [],
                "MX": ["10 mx1.reg.ru.", "20 mx2.reg.ru."],
                "TXT": ["v=spf1 ip4:185.12.34.0/24 ~all"],
                "NS": ["ns1.reg.ru.", "ns2.reg.ru."],
                "SOA": [],
                "CNAME": [],
            },
            "reverse_dns": {},
            "analysis": {
                "has_ipv4": True,
                "has_ipv6": False,
                "has_mail": True,
                "has_spf": True,
                "has_dkim": False,
                "mail_provider": "reg.ru",
                "hosting_provider": "reg.ru",
            },
        },
        "ya.ru": {
            "domain": "ya.ru",
            "records": {
                "A": ["5.255.255.80"],
                "AAAA": ["2a02:6b8::2:242"],
                "MX": ["10 mx.yandex.net."],
                "TXT": [
                    "v=spf1 redirect=_spf.yandex.net",
                    "globalsign-smime-dv=CDYX+Xw9PG...",
                ],
                "NS": ["ns1.yandex.ru.", "ns2.yandex.ru."],
                "SOA": ["ns1.yandex.ru. dns-admin.yandex.ru. 2024010101 900 600 2592000 900"],
                "CNAME": [],
            },
            "reverse_dns": {
                "5.255.255.80": ["ya.ru"],
            },
            "analysis": {
                "has_ipv4": True,
                "has_ipv6": True,
                "has_mail": True,
                "has_spf": True,
                "has_dkim": False,
                "mail_provider": "yandex",
                "hosting_provider": "unknown",
            },
        },
        "google.com": {
            "domain": "google.com",
            "records": {
                "A": ["142.250.185.78"],
                "AAAA": ["2a00:1450:4001:828::200e"],
                "MX": ["10 smtp.google.com."],
                "TXT": [
                    "v=spf1 include:_spf.google.com ~all",
                    "globalsign-smime-dv=CDYX+Xw9PG...",
                ],
                "NS": ["ns1.google.com.", "ns2.google.com.", "ns3.google.com.", "ns4.google.com."],
                "SOA": ["ns1.google.com. dns-admin.google.com. 2024010101 900 600 2592000 900"],
                "CNAME": [],
            },
            "reverse_dns": {
                "142.250.185.78": ["bud02s34-in-f14.1e100.net"],
            },
            "analysis": {
                "has_ipv4": True,
                "has_ipv6": True,
                "has_mail": True,
                "has_spf": True,
                "has_dkim": False,
                "mail_provider": "google",
                "hosting_provider": "unknown",
            },
        },
    }

    @property
    def name(self) -> str:
        return "dns"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock DNS данные."""
        domain = query.params.get("domain")
        if not domain:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="Domain is required",
            )

        await asyncio.sleep(0.05)

        if domain in self.MOCK_DATA:
            return ConnectorResult(
                success=True,
                data=self.MOCK_DATA[domain],
                source=f"{self.name}:mock",
                confidence=1.0,
            )

        # Для неизвестных доменов возвращаем пустой результат
        return ConnectorResult(
            success=True,
            data={
                "domain": domain,
                "records": {rt: [] for rt in RECORD_TYPES},
                "reverse_dns": {},
                "analysis": {
                    "has_ipv4": False,
                    "has_ipv6": False,
                    "has_mail": False,
                    "has_spf": False,
                    "has_dkim": False,
                    "mail_provider": None,
                    "hosting_provider": None,
                },
            },
            source=f"{self.name}:mock",
            confidence=0.5,
        )

    async def health_check(self) -> bool:
        return True


class DNSAnalyzer:
    """Анализ DNS данных для выявления связей и Red Flags."""

    def find_related_domains(
        self,
        dns_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Найти связи между доменами через общие IP и серверы имен."""
        connections = []

        # Группируем по IP
        ip_to_domains: dict[str, list[str]] = {}
        for result in dns_results:
            domain = result.get("domain")
            a_records = result.get("records", {}).get("A", [])

            for ip in a_records:
                if ip not in ip_to_domains:
                    ip_to_domains[ip] = []
                ip_to_domains[ip].append(domain)

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
        for result in dns_results:
            domain = result.get("domain")
            ns_records = result.get("records", {}).get("NS", [])

            for ns in ns_records:
                ns = ns.rstrip(".")
                if ns not in ns_to_domains:
                    ns_to_domains[ns] = []
                ns_to_domains[ns].append(domain)

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
        for result in dns_results:
            domain = result.get("domain")
            mx_records = result.get("records", {}).get("MX", [])

            for mx in mx_records:
                # Извлекаем домен из MX записи (формат: "10 mx.yandex.net.")
                parts = mx.split()
                if len(parts) >= 2:
                    mx_domain = parts[1].rstrip(".")
                    if mx_domain not in mx_to_domains:
                        mx_to_domains[mx_domain] = []
                    mx_to_domains[mx_domain].append(domain)

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

    def find_red_flags(self, dns_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Найти Red Flags в DNS данных."""
        red_flags = []
        analysis = dns_data.get("analysis", {})

        # Проверка SPF
        if not analysis.get("has_spf"):
            red_flags.append({
                "id": "DNS_NO_SPF",
                "priority": "LOW",
                "description": "Домен не настроил SPF запись (уязвим для спуфинга)",
                "evidence": {"domain": dns_data.get("domain")},
            })

        # Проверка DMARC (ищем в TXT записях)
        has_dmarc = False
        for txt in dns_data.get("records", {}).get("TXT", []):
            if "v=DMARC1" in txt:
                has_dmarc = True
                break

        if not has_dmarc:
            red_flags.append({
                "id": "DNS_NO_DMARC",
                "priority": "LOW",
                "description": "Домен не настроил DMARC запись",
                "evidence": {"domain": dns_data.get("domain")},
            })

        # Проверка IPv6
        if not analysis.get("has_ipv6"):
            red_flags.append({
                "id": "DNS_NO_IPV6",
                "priority": "LOW",
                "description": "Домен не поддерживает IPv6",
                "evidence": {"domain": dns_data.get("domain")},
            })

        return red_flags
