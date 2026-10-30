"""Integration tests — реальные API вызовы.

WHOIS и DNS работают бесплатно без ключей.
Shodan использует ключ из .env.

⚠️ Эти тесты зависят от сети и внешних сервисов.
   Запуск: pytest -m integration_real --run-real-api
"""

import pytest
import os

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.whois import WhoisConnector
from osint_agent.connectors.dns import DNSConnector
from osint_agent.connectors.shodan import ShodanConnector
from osint_agent.models import ConnectorQuery


# Пропускаем если не передан флаг --run-real-api
pytestmark = pytest.mark.skipif(
    "--run-real-api" not in os.environ.get("PYTEST_ADDOPTS", "")
    and "--run-real-api" not in os.sys.argv,
    reason="Real API tests disabled (pass --run-real-api)",
)


@pytest.fixture
def hub():
    h = DataConnectorHub()
    h.register(WhoisConnector())
    h.register(DNSConnector())
    h.register(ShodanConnector())
    return h


# ---------------------------------------------------------------------------
# WHOIS — реальные запросы (бесплатно)
# ---------------------------------------------------------------------------

@pytest.mark.integration_real
class TestRealWhois:
    """WHOIS запросы к реальным доменам."""

    @pytest.mark.asyncio
    async def test_whois_yandex(self, hub):
        """WHOIS для ya.ru — должен вернуть registrar."""
        result = await hub.fetch("whois", {"domain": "ya.ru"})
        assert result.success
        assert result.data["domain"] == "ya.ru"
        assert result.data["registrar"] is not None

    @pytest.mark.asyncio
    async def test_whois_google(self, hub):
        """WHOIS для google.com."""
        result = await hub.fetch("whois", {"domain": "google.com"})
        assert result.success
        assert result.data["registrar"] is not None

    @pytest.mark.asyncio
    async def test_whois_nonexistent(self, hub):
        """WHOIS для несуществующего домена."""
        result = await hub.fetch("whois", {"domain": "thisdomaindoesnotexist12345.xyz"})
        # Может вернуть ошибку или пустые данные — оба варианта ОК
        assert result is not None


# ---------------------------------------------------------------------------
# DNS — реальные запросы (бесплатно)
# ---------------------------------------------------------------------------

@pytest.mark.integration_real
class TestRealDNS:
    """DNS запросы к реальным доменам."""

    @pytest.mark.asyncio
    async def test_dns_yandex(self, hub):
        """DNS для ya.ru — A, MX, NS записи."""
        result = await hub.fetch("dns", {"domain": "ya.ru"})
        assert result.success
        assert len(result.data["records"]["A"]) > 0
        assert len(result.data["records"]["MX"]) > 0
        assert len(result.data["records"]["NS"]) > 0

    @pytest.mark.asyncio
    async def test_dns_google(self, hub):
        """DNS для google.com."""
        result = await hub.fetch("dns", {"domain": "google.com"})
        assert result.success
        assert len(result.data["records"]["A"]) > 0

    @pytest.mark.asyncio
    async def test_dns_reverse_lookup(self, hub):
        """Обратный DNS поиск для IP Яндекса."""
        result = await hub.fetch("dns", {"domain": "ya.ru"})
        assert result.success
        # Проверяем что reverse_dns не пустой (если PTR настроен)
        # Не все IP имеют PTR, поэтому просто проверяем структуру
        assert "reverse_dns" in result.data

    @pytest.mark.asyncio
    async def test_dns_analysis(self, hub):
        """DNS analysis содержит has_mail, has_spf."""
        result = await hub.fetch("dns", {"domain": "ya.ru"})
        assert result.success
        analysis = result.data["analysis"]
        assert "has_mail" in analysis
        assert "has_spf" in analysis


# ---------------------------------------------------------------------------
# Shodan — реальные запросы (требует API ключ)
# ---------------------------------------------------------------------------

@pytest.mark.integration_real
class TestRealShodan:
    """Shodan запросы с реальным API ключом."""

    @pytest.mark.asyncio
    async def test_shodan_host_info(self, hub):
        """Shodan для IP Google DNS."""
        from osint_agent.config import settings
        if not settings.shodan_api_key:
            pytest.skip("SHODAN_API_KEY not set")

        result = await hub.fetch("shodan", {"ip": "8.8.8.8"})
        assert result.success
        assert result.data.get("ip") == "8.8.8.8"
        assert result.data.get("org") is not None

    @pytest.mark.asyncio
    async def test_shodan_domain_info(self, hub):
        """Shodan для домена."""
        from osint_agent.config import settings
        if not settings.shodan_api_key:
            pytest.skip("SHODAN_API_KEY not set")

        result = await hub.fetch("shodan", {"domain": "google.com"})
        assert result.success
        assert result.data.get("domain") == "google.com"

    @pytest.mark.asyncio
    async def test_shodan_graceful_skip_without_key(self):
        """Shodan gracefully пропускается без API ключа."""
        # Создаём hub без ключа
        original_key = os.environ.get("SHODAN_API_KEY")
        os.environ.pop("SHODAN_API_KEY", None)

        try:
            from osint_agent.config import Settings
            # Временно подменяем settings
            from osint_agent.connectors import shodan as shodan_module
            import osint_agent.config as config_module

            original_settings = config_module.settings
            config_module.settings = Settings()

            connector = ShodanConnector()
            result = await connector.fetch(
                ConnectorQuery(query_type="shodan", params={"ip": "8.8.8.8"})
            )

            assert result.success  # Не ошибка — Shodan необязателен
            assert result.data.get("skipped") is True

            config_module.settings = original_settings
        finally:
            if original_key:
                os.environ["SHODAN_API_KEY"] = original_key


# ---------------------------------------------------------------------------
# Полный пайплайн с реальными API
# ---------------------------------------------------------------------------

@pytest.mark.integration_real
class TestRealFullPipeline:
    """Полный пайплайн: WHOIS + DNS + Shodan → Graph."""

    @pytest.mark.asyncio
    async def test_build_graph_real_yandex(self, hub):
        """Граф для Яндекса на реальных данных."""
        from osint_agent.graph.builder import CompanyGraphBuilder

        builder = CompanyGraphBuilder(hub)
        graph = await builder.build(
            company_name="Яндекс",
            inn="7736207543",
            website="https://ya.ru",
        )

        node_types = {n.type for n in graph.nodes.values()}
        assert "company" in node_types
        assert "domain" in node_types

        stats = graph.get_stats()
        assert stats["nodes"] >= 2
        assert stats["edges"] >= 1

    @pytest.mark.asyncio
    async def test_build_graph_real_google(self, hub):
        """Граф для Google на реальных данных."""
        from osint_agent.graph.builder import CompanyGraphBuilder

        builder = CompanyGraphBuilder(hub)
        graph = await builder.build(
            company_name="Google",
            inn="0000000000",
            website="https://google.com",
        )

        node_types = {n.type for n in graph.nodes.values()}
        assert "company" in node_types
        assert "domain" in node_types
