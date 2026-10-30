"""Tests for WHOIS and DNS connectors."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from osint_agent.connectors.whois import WhoisConnector, WhoisAnalyzer
from osint_agent.connectors.dns import DNSConnector, MockDNSConnector, DNSAnalyzer
from osint_agent.models import ConnectorQuery


@pytest.mark.unit
class TestWhoisConnector:
    """Unit tests for WHOIS normalization; live lookups are in integration/test_real_api.py."""

    @pytest.fixture
    def connector(self, monkeypatch):
        connector = WhoisConnector()
        monkeypatch.setattr(connector, "_whois_lookup", AsyncMock(return_value={
            "registrar": "Example Registrar", "creation_date": "2000-01-01T00:00:00",
            "registrant_name": "Example Owner", "registrant_org": "Example Organization",
        }))
        return connector

    @pytest.fixture
    def analyzer(self):
        return WhoisAnalyzer()

    @pytest.mark.asyncio
    async def test_fetch_known_domain(self, connector):
        """Test WHOIS lookup for known domain."""
        query = ConnectorQuery(
            query_type="whois",
            params={"domain": "google.com"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["domain"] == "google.com"
        assert result.data["registrar"] is not None
        assert result.data["creation_date"] is not None

    @pytest.mark.asyncio
    async def test_fetch_without_domain(self, connector):
        """Test WHOIS lookup without domain."""
        query = ConnectorQuery(
            query_type="whois",
            params={},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "Domain is required" in result.error

    @pytest.mark.asyncio
    async def test_fetch_private_registration(self, connector):
        """Test WHOIS lookup for domain with private registration."""
        connector._whois_lookup.return_value = {
            "registrar": "Example Registrar", "registrant_name": "REDACTED FOR PRIVACY",
            "registrant_org": "Privacy Protect",
        }
        query = ConnectorQuery(
            query_type="whois",
            params={"domain": "example.com"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["is_private_registration"] is True
        assert result.data["registrant_name"] is None

    def test_analyze_recently_registered(self, analyzer):
        """Test Red Flag for recently registered domain."""
        whois_data = {
            "domain": "new-domain.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=335)).isoformat(),
            "is_private_registration": False,
            "dnssec": True,
        }

        flags = analyzer.analyze(whois_data)

        flag_ids = [f["id"] for f in flags]
        assert "DOMAIN_RECENTLY_REGISTERED" in flag_ids

    def test_analyze_expiring_soon(self, analyzer):
        """Test Red Flag for domain expiring soon."""
        whois_data = {
            "domain": "expiring.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=365)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=15)).isoformat(),
            "is_private_registration": False,
            "dnssec": True,
        }

        flags = analyzer.analyze(whois_data)

        flag_ids = [f["id"] for f in flags]
        assert "DOMAIN_EXPIRING_SOON" in flag_ids

    def test_analyze_private_registration(self, analyzer):
        """Test Red Flag for private registration."""
        whois_data = {
            "domain": "private.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=365)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),
            "is_private_registration": True,
            "dnssec": True,
        }

        flags = analyzer.analyze(whois_data)

        flag_ids = [f["id"] for f in flags]
        assert "DOMAIN_PRIVATE_REGISTRATION" in flag_ids

    def test_analyze_no_dnssec(self, analyzer):
        """Test Red Flag for no DNSSEC."""
        whois_data = {
            "domain": "no-dnssec.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=365)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),
            "is_private_registration": False,
            "dnssec": False,
        }

        flags = analyzer.analyze(whois_data)

        flag_ids = [f["id"] for f in flags]
        assert "DOMAIN_NO_DNSSEC" in flag_ids

    def test_analyze_multiple_flags(self, analyzer):
        """Test multiple Red Flags."""
        whois_data = {
            "domain": "problematic.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=15)).isoformat(),
            "is_private_registration": True,
            "dnssec": False,
        }

        flags = analyzer.analyze(whois_data)

        flag_ids = [f["id"] for f in flags]
        assert "DOMAIN_RECENTLY_REGISTERED" in flag_ids
        assert "DOMAIN_EXPIRING_SOON" in flag_ids
        assert "DOMAIN_PRIVATE_REGISTRATION" in flag_ids
        assert "DOMAIN_NO_DNSSEC" in flag_ids
        assert len(flags) == 4

    def test_analyze_clean_domain(self, analyzer):
        """Test no Red Flags for clean domain."""
        whois_data = {
            "domain": "clean.ru",
            "creation_date": (datetime.utcnow() - timedelta(days=1000)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),
            "is_private_registration": False,
            "dnssec": True,
        }

        flags = analyzer.analyze(whois_data)

        assert len(flags) == 0


@pytest.mark.unit
class TestMockDNSConnector:
    """Tests for MockDNSConnector."""

    @pytest.fixture
    def connector(self):
        return MockDNSConnector()

    @pytest.mark.asyncio
    async def test_fetch_known_domain(self, connector):
        """Test DNS lookup for known domain."""
        query = ConnectorQuery(
            query_type="dns",
            params={"domain": "ya.ru"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["domain"] == "ya.ru"
        assert "5.255.255.80" in result.data["records"]["A"]
        assert "10 mx.yandex.net." in result.data["records"]["MX"]

    @pytest.mark.asyncio
    async def test_fetch_google(self, connector):
        """Test DNS lookup for Google."""
        query = ConnectorQuery(
            query_type="dns",
            params={"domain": "google.com"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["domain"] == "google.com"
        assert "142.250.185.78" in result.data["records"]["A"]
        assert result.data["analysis"]["mail_provider"] == "google"

    @pytest.mark.asyncio
    async def test_fetch_unknown_domain(self, connector):
        """Test DNS lookup for unknown domain."""
        query = ConnectorQuery(
            query_type="dns",
            params={"domain": "unknown-domain-12345.ru"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["domain"] == "unknown-domain-12345.ru"
        assert result.data["records"]["A"] == []

    @pytest.mark.asyncio
    async def test_fetch_without_domain(self, connector):
        """Test DNS lookup without domain."""
        query = ConnectorQuery(
            query_type="dns",
            params={},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "Domain is required" in result.error


@pytest.mark.unit
class TestDNSAnalyzer:
    """Tests for DNSAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return DNSAnalyzer()

    def test_find_related_domains_same_ip(self, analyzer):
        """Test finding domains on same IP."""
        dns_results = [
            {
                "domain": "site1.ru",
                "records": {"A": ["1.2.3.4"], "NS": [], "MX": []},
            },
            {
                "domain": "site2.ru",
                "records": {"A": ["1.2.3.4"], "NS": [], "MX": []},
            },
            {
                "domain": "site3.ru",
                "records": {"A": ["5.6.7.8"], "NS": [], "MX": []},
            },
        ]

        connections = analyzer.find_related_domains(dns_results)

        # site1.ru и site2.ru на одном IP
        assert len(connections) == 1
        assert connections[0]["type"] == "same_ip"
        assert connections[0]["value"] == "1.2.3.4"

    def test_find_related_domains_same_ns(self, analyzer):
        """Test finding domains with same nameserver."""
        dns_results = [
            {
                "domain": "site1.ru",
                "records": {"A": ["1.2.3.4"], "NS": ["ns1.hosting.ru."], "MX": []},
            },
            {
                "domain": "site2.ru",
                "records": {"A": ["5.6.7.8"], "NS": ["ns1.hosting.ru."], "MX": []},
            },
        ]

        connections = analyzer.find_related_domains(dns_results)

        assert len(connections) == 1
        assert connections[0]["type"] == "same_nameserver"
        assert connections[0]["value"] == "ns1.hosting.ru"

    def test_find_related_domains_same_mx(self, analyzer):
        """Test finding domains with same mail server."""
        dns_results = [
            {
                "domain": "site1.ru",
                "records": {"A": ["1.2.3.4"], "NS": [], "MX": ["10 mx.yandex.net."]},
            },
            {
                "domain": "site2.ru",
                "records": {"A": ["5.6.7.8"], "NS": [], "MX": ["10 mx.yandex.net."]},
            },
        ]

        connections = analyzer.find_related_domains(dns_results)

        assert len(connections) == 1
        assert connections[0]["type"] == "same_mail_server"
        assert connections[0]["value"] == "mx.yandex.net"

    def test_find_related_domains_no_connections(self, analyzer):
        """Test no connections found."""
        dns_results = [
            {
                "domain": "site1.ru",
                "records": {"A": ["1.2.3.4"], "NS": ["ns1.host1.ru."], "MX": ["10 mx.host1.ru."]},
            },
            {
                "domain": "site2.ru",
                "records": {"A": ["5.6.7.8"], "NS": ["ns1.host2.ru."], "MX": ["10 mx.host2.ru."]},
            },
        ]

        connections = analyzer.find_related_domains(dns_results)

        assert len(connections) == 0

    def test_find_red_flags_no_spf(self, analyzer):
        """Test Red Flag for no SPF."""
        dns_data = {
            "domain": "no-spf.ru",
            "records": {"TXT": []},
            "analysis": {"has_spf": False},
        }

        flags = analyzer.find_red_flags(dns_data)

        flag_ids = [f["id"] for f in flags]
        assert "DNS_NO_SPF" in flag_ids

    def test_find_red_flags_no_dmarc(self, analyzer):
        """Test Red Flag for no DMARC."""
        dns_data = {
            "domain": "no-dmarc.ru",
            "records": {"TXT": ["v=spf1 include:_spf.google.com ~all"]},
            "analysis": {"has_spf": True},
        }

        flags = analyzer.find_red_flags(dns_data)

        flag_ids = [f["id"] for f in flags]
        assert "DNS_NO_DMARC" in flag_ids

    def test_find_red_flags_no_ipv6(self, analyzer):
        """Test Red Flag for no IPv6."""
        dns_data = {
            "domain": "no-ipv6.ru",
            "records": {"TXT": ["v=spf1 include:_spf.google.com ~all", "v=DMARC1; p=none"]},
            "analysis": {"has_spf": True, "has_ipv6": False},
        }

        flags = analyzer.find_red_flags(dns_data)

        flag_ids = [f["id"] for f in flags]
        assert "DNS_NO_IPV6" in flag_ids

    def test_find_red_flags_clean(self, analyzer):
        """Test no Red Flags for clean domain."""
        dns_data = {
            "domain": "clean.ru",
            "records": {
                "TXT": [
                    "v=spf1 include:_spf.google.com ~all",
                    "v=DMARC1; p=none",
                ],
            },
            "analysis": {"has_spf": True, "has_ipv6": True},
        }

        flags = analyzer.find_red_flags(dns_data)

        assert len(flags) == 0
