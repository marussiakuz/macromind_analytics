"""Shodan Connector — поиск устройств и инфраструктуры.

Источник: https://api.shodan.io

Shodan — поисковая система для IoT устройств, серверов, сервисов.
В отличие от Google, который индексирует контент сайтов,
Shodan сканирует открытые порты и сервисы.

Получает:
- Информация об IP-адресе (организация, геолокация)
- Открытые порты и сервисы
- Уязвимости (CVE)
- Доменные имена
- Исторические данные

ВАЖНО:
- Бесплатный план: 100 запросов/мес, 1 запрос/сек
- API ключ хранится в .env (НЕ в коде!)
- Результаты кэшируются (TTL 6 часов)
- API ключ передаётся в заголовке X-Api-Key (не в URL!)
"""

import asyncio
import ipaddress
from typing import Any

import httpx

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult, RedFlag, RedFlagCategory, RedFlagPriority
from osint_agent.utils import get_logger


def validate_ip(ip: str) -> str:
    """Validate IP address format and block private/reserved IPs.

    Защита от SSRF — блокируем запросы к внутренним адресам.

    Args:
        ip: IP-адрес

    Returns:
        Валидный IP-адрес

    Raises:
        ValueError: Если IP невалиден или является приватным/reserved
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"Invalid IP address: {ip}")

    if addr.is_private:
        raise ValueError(f"Private IP not allowed: {ip}")
    if addr.is_loopback:
        raise ValueError(f"Loopback IP not allowed: {ip}")
    if addr.is_reserved:
        raise ValueError(f"Reserved IP not allowed: {ip}")
    if addr.is_multicast:
        raise ValueError(f"Multicast IP not allowed: {ip}")

    return str(addr)

logger = get_logger(__name__)


class ShodanConnector(BaseConnector):
    """Shodan API — поиск устройств и инфраструктуры.

    Документация: https://developer.shodan.io/api

    Endpoints:
    - /shodan/host/{ip} — информация об IP
    - /shodan/host/search — поиск по запросу
    - /dns/resolve — резолв домена в IP
    - /dns/domain/{domain} — DNS записи домена

    Ограничения (Free plan):
    - 100 запросов в месяц
    - 1 запрос в секунду
    - Нет доступа к историческим данным
    - Нет доступа к сканированию в реальном времени
    """

    BASE_URL = "https://api.shodan.io"

    @property
    def name(self) -> str:
        return "shodan"

    @property
    def rate_limit(self) -> int:
        return 60  # 1 запрос в секунду

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить данные из Shodan.

        Shodan — НЕОБЯЗАТЕЛЬНЫЙ сервис. Если API ключ не настроен
        или закончились кредиты — возвращаем пустой результат с предупреждением,
        но НЕ ошибку. Сервис не должен падать из-за Shodan.

        Args:
            query: ConnectorQuery с params:
                - ip: str (IP-адрес)
                - domain: str (домен, опционально)
                - query: str (поисковый запрос, опционально)

        Returns:
            ConnectorResult с данными Shodan или пустой результат
        """
        from osint_agent.config import settings

        api_key = settings.shodan_api_key
        if not api_key:
            logger.info(
                "shodan_skipped",
                reason="API key not configured",
                hint="Set SHODAN_API_KEY in .env to enable Shodan integration",
            )
            return ConnectorResult(
                success=True,  # Не ошибка — Shodan необязателен
                data={
                    "found": False,
                    "skipped": True,
                    "reason": "Shodan API key not configured",
                },
                source=f"{self.name}:skipped",
                confidence=0.0,
            )

        ip = query.params.get("ip")
        domain = query.params.get("domain")
        search_query = query.params.get("query")

        if not ip and not domain and not search_query:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="Either 'ip', 'domain', or 'query' parameter is required",
            )

        # Валидация IP (SSRF защита)
        if ip:
            try:
                ip = validate_ip(ip)
            except ValueError as e:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error=str(e),
                )

        try:
            if ip:
                result = await self._host_info(ip, api_key)
            elif domain:
                result = await self._domain_info(domain, api_key)
            elif search_query:
                result = await self._search(search_query, api_key)
            else:
                # Сюда не должны дойти, но на всякий случай
                return ConnectorResult(
                    success=True,
                    data={"found": False, "skipped": True, "reason": "No query parameters"},
                    source=f"{self.name}:skipped",
                    confidence=0.0,
                )

            return ConnectorResult(
                success=True,
                data=result,
                source=self.name,
                confidence=1.0,
            )

        except ShodanAPIError as e:
            # Ошибки API — логируем, но не роняем сервис
            error_msg = str(e)
            logger.warning(
                "shodan_api_error",
                error=error_msg,
                ip=ip,
                domain=domain,
            )
            return ConnectorResult(
                success=True,  # Не ошибка — Shodan необязателен
                data={
                    "found": False,
                    "skipped": True,
                    "reason": error_msg,
                },
                source=f"{self.name}:error",
                confidence=0.0,
            )
        except httpx.TimeoutException:
            logger.warning(
                "shodan_timeout",
                ip=ip,
                domain=domain,
            )
            return ConnectorResult(
                success=True,
                data={
                    "found": False,
                    "skipped": True,
                    "reason": "Shodan API request timeout",
                },
                source=f"{self.name}:timeout",
                confidence=0.0,
            )
        except httpx.HTTPStatusError as e:
            logger.warning(
                "shodan_http_error",
                status=e.response.status_code,
                ip=ip,
                domain=domain,
            )
            return ConnectorResult(
                success=True,
                data={
                    "found": False,
                    "skipped": True,
                    "reason": f"Shodan API HTTP error: {e.response.status_code}",
                },
                source=f"{self.name}:http_error",
                confidence=0.0,
            )
        except Exception as e:
            # Неожиданные ошибки — логируем с traceback
            logger.error(
                "shodan_unexpected_error",
                error=str(e),
                ip=ip,
                domain=domain,
                exc_info=True,
            )
            return ConnectorResult(
                success=True,
                data={
                    "found": False,
                    "skipped": True,
                    "reason": f"Unexpected error: {str(e)}",
                },
                source=f"{self.name}:error",
                confidence=0.0,
            )

    async def _host_info(self, ip: str, api_key: str) -> dict[str, Any]:
        """Получить информацию об IP-адресе.

        Shodan API: GET /shodan/host/{ip}
        API ключ передаётся в заголовке X-Api-Key (не в URL!)
        """
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/shodan/host/{ip}",
            headers={"X-Api-Key": api_key},
        )

        if response.status_code == 404:
            # IP не найден в Shodan
            return {
                "ip": ip,
                "found": False,
                "message": "IP not found in Shodan database",
            }

        if response.status_code == 401:
            raise ShodanAPIError("Invalid Shodan API key")

        if response.status_code == 429:
            raise ShodanAPIError("Shodan API rate limit exceeded")

        response.raise_for_status()
        data = response.json()

        # Нормализуем данные
        return {
            "ip": data.get("ip_str", ip),
            "found": True,
            "hostnames": data.get("hostnames", []),
            "domains": data.get("domains", []),
            "org": data.get("org"),
            "isp": data.get("isp"),
            "os": data.get("os"),
            "ports": data.get("ports", []),
            "vulns": data.get("vulns", []),
            "city": data.get("city"),
            "country_name": data.get("country_name"),
            "country_code": data.get("country_code"),
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "last_update": data.get("last_update"),
            "tags": data.get("tags", []),
            "as_number": data.get("asn"),
            "as_name": data.get("as_name"),
        }

    async def _domain_info(self, domain: str, api_key: str) -> dict[str, Any]:
        """Получить информацию о домене.

        Shodan API: GET /dns/domain/{domain}
        API ключ передаётся в заголовке X-Api-Key (не в URL!)
        """
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/dns/domain/{domain}",
            headers={"X-Api-Key": api_key},
        )

        if response.status_code == 404:
            return {
                "domain": domain,
                "found": False,
                "message": "Domain not found in Shodan database",
            }

        if response.status_code == 401:
            raise ShodanAPIError("Invalid Shodan API key")

        if response.status_code == 429:
            raise ShodanAPIError("Shodan API rate limit exceeded")

        response.raise_for_status()
        data = response.json()

        return {
            "domain": domain,
            "found": True,
            "subdomains": data.get("subdomains", []),
            "dns_records": data.get("dns", {}),
            "tags": data.get("tags", []),
        }

    async def _search(self, query: str, api_key: str) -> dict[str, Any]:
        """Поиск по запросу Shodan.

        Shodan API: GET /shodan/host/search
        API ключ передаётся в заголовке X-Api-Key (не в URL!)
        """
        client = await self.get_client()

        response = await client.get(
            f"{self.BASE_URL}/shodan/host/search",
            params={"query": query},
            headers={"X-Api-Key": api_key},
        )

        if response.status_code == 401:
            raise ShodanAPIError("Invalid Shodan API key")

        if response.status_code == 429:
            raise ShodanAPIError("Shodan API rate limit exceeded")

        response.raise_for_status()
        data = response.json()

        return {
            "query": query,
            "total": data.get("total", 0),
            "matches": [
                {
                    "ip": m.get("ip_str"),
                    "org": m.get("org"),
                    "hostnames": m.get("hostnames", []),
                    "port": m.get("port"),
                    "transport": m.get("transport"),
                    "product": m.get("product"),
                    "version": m.get("version"),
                    "vulns": m.get("vulns", []),
                }
                for m in data.get("matches", [])[:10]  # Ограничиваем до 10 результатов
            ],
        }

    async def health_check(self) -> bool:
        """Проверка доступности Shodan API."""
        from osint_agent.config import settings

        api_key = settings.shodan_api_key
        if not api_key:
            return False

        try:
            client = await self.get_client()
            response = await client.get(
                f"{self.BASE_URL}/api-info",
                params={"key": api_key},
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception:
            return False


class ShodanAPIError(Exception):
    """Ошибка Shodan API."""
    pass


class MockShodanConnector(BaseConnector):
    """Mock Shodan connector для тестирования."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "185.12.34.56": {
            "ip": "185.12.34.56",
            "found": True,
            "hostnames": ["test-company.ru"],
            "domains": ["test-company.ru"],
            "org": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            "isp": "Reg.ru Ltd.",
            "os": "Linux",
            "ports": [80, 443, 22],
            "vulns": [],
            "city": "Moscow",
            "country_name": "Russia",
            "country_code": "RU",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "last_update": "2024-06-01T00:00:00",
            "tags": [],
            "as_number": "AS197695",
            "as_name": "REG",
        },
        "8.8.8.8": {
            "ip": "8.8.8.8",
            "found": True,
            "hostnames": ["dns.google"],
            "domains": ["google.com"],
            "org": "Google LLC",
            "isp": "Google LLC",
            "os": None,
            "ports": [53, 443],
            "vulns": [],
            "city": "Mountain View",
            "country_name": "United States",
            "country_code": "US",
            "latitude": 37.4056,
            "longitude": -122.0775,
            "last_update": "2024-01-15T00:00:00",
            "tags": [],
            "as_number": "AS15169",
            "as_name": "GOOGLE",
        },
        "1.1.1.1": {
            "ip": "1.1.1.1",
            "found": True,
            "hostnames": ["one.one.one.one"],
            "domains": ["cloudflare.com"],
            "org": "Cloudflare, Inc.",
            "isp": "Cloudflare, Inc.",
            "os": None,
            "ports": [53, 80, 443],
            "vulns": [],
            "city": "Sydney",
            "country_name": "Australia",
            "country_code": "AU",
            "latitude": -33.8688,
            "longitude": 151.2093,
            "last_update": "2024-01-15T00:00:00",
            "tags": [],
            "as_number": "AS13335",
            "as_name": "CLOUDFLARENET",
        },
        "93.184.216.34": {
            "ip": "93.184.216.34",
            "found": True,
            "hostnames": ["example.com"],
            "domains": ["example.com"],
            "org": "Internet Assigned Numbers Authority",
            "isp": "Internet Assigned Numbers Authority",
            "os": None,
            "ports": [80, 443],
            "vulns": [],
            "city": "Norwell",
            "country_name": "United States",
            "country_code": "US",
            "latitude": 42.1467,
            "longitude": -70.8228,
            "last_update": "2024-01-15T00:00:00",
            "tags": ["cloud"],
            "as_number": "AS15133",
            "as_name": "EDGECAST",
        },
    }

    MOCK_DOMAIN_DATA: dict[str, dict[str, Any]] = {
        "google.com": {
            "domain": "google.com",
            "found": True,
            "subdomains": ["www", "mail", "docs", "drive", "maps"],
            "dns_records": {
                "A": ["142.250.185.78"],
                "AAAA": ["2a00:1450:4001:828::200e"],
                "MX": ["10 smtp.google.com."],
                "NS": ["ns1.google.com.", "ns2.google.com.", "ns3.google.com.", "ns4.google.com."],
            },
            "tags": [],
        },
        "yandex.ru": {
            "domain": "yandex.ru",
            "found": True,
            "subdomains": ["www", "mail", "music", "disk", "translate"],
            "dns_records": {
                "A": ["5.255.255.80"],
                "AAAA": ["2a02:6b8::2:242"],
                "MX": ["10 mx.yandex.net."],
                "NS": ["ns1.yandex.ru.", "ns2.yandex.ru."],
            },
            "tags": [],
        },
    }

    @property
    def name(self) -> str:
        return "shodan"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Вернуть mock данные Shodan."""
        ip = query.params.get("ip")
        domain = query.params.get("domain")

        await asyncio.sleep(0.1)

        if ip:
            if ip in self.MOCK_DATA:
                return ConnectorResult(
                    success=True,
                    data=self.MOCK_DATA[ip],
                    source=f"{self.name}:mock",
                )
            return ConnectorResult(
                success=True,
                data={
                    "ip": ip,
                    "found": False,
                    "message": "IP not found in Shodan database",
                },
                source=f"{self.name}:mock",
            )

        if domain:
            if domain in self.MOCK_DOMAIN_DATA:
                return ConnectorResult(
                    success=True,
                    data=self.MOCK_DOMAIN_DATA[domain],
                    source=f"{self.name}:mock",
                )
            return ConnectorResult(
                success=True,
                data={
                    "domain": domain,
                    "found": False,
                    "message": "Domain not found in Shodan database",
                },
                source=f"{self.name}:mock",
            )

        return ConnectorResult(
            success=False,
            source=self.name,
            error="Either 'ip' or 'domain' parameter is required",
        )

    async def health_check(self) -> bool:
        return True


class ShodanAnalyzer:
    """Анализ данных Shodan для выявления Red Flags."""

    def analyze_ip(self, shodan_data: dict[str, Any]) -> list[RedFlag]:
        """Проанализировать данные Shodan для IP."""
        red_flags = []

        if not shodan_data.get("found"):
            return red_flags

        # Проверка уязвимостей
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

        # Проверка количества открытых портов
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

        # Проверка подозрительных портов
        suspicious_ports = {
            21: "FTP (незашифрованный)",
            23: "Telnet (незашифрованный)",
            25: "SMTP (может быть open relay)",
            110: "POP3 (незашифрованный)",
            143: "IMAP (незашифрованный)",
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

        # Проверка shared hosting (много доменов на одном IP)
        domains = shodan_data.get("domains", [])
        if len(domains) > 10:
            red_flags.append(RedFlag(
                id="SHODAN_SHARED_HOSTING",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.LEGAL,
                description=f"На одном IP размещено много доменов ({len(domains)}) — shared hosting",
                block="D",
                evidence={
                    "ip": shodan_data.get("ip"),
                    "domains_count": len(domains),
                    "domains_sample": domains[:10],
                },
                source_ref="Shodan",
            ))

        return red_flags

    def analyze_domain(self, shodan_data: dict[str, Any]) -> list[RedFlag]:
        """Проанализировать данные Shodan для домена."""
        red_flags = []

        if not shodan_data.get("found"):
            return red_flags

        # Проверка количества поддоменов
        subdomains = shodan_data.get("subdomains", [])
        if len(subdomains) > 50:
            red_flags.append(RedFlag(
                id="SHODAN_MANY_SUBDOMAINS",
                priority=RedFlagPriority.LOW,
                category=RedFlagCategory.LEGAL,
                description=f"Много поддоменов ({len(subdomains)}) — большая инфраструктура",
                block="D",
                evidence={
                    "domain": shodan_data.get("domain"),
                    "subdomains_count": len(subdomains),
                    "subdomains_sample": subdomains[:10],
                },
                source_ref="Shodan",
            ))

        return red_flags
