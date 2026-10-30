"""Tests for Shodan Connector."""

import pytest
from unittest.mock import AsyncMock, patch

from osint_agent.connectors.shodan import ShodanConnector, MockShodanConnector, ShodanAnalyzer
from osint_agent.models import ConnectorQuery, RedFlagPriority


@pytest.mark.unit
class TestMockShodanConnector:
    """Tests for MockShodanConnector."""

    @pytest.fixture
    def connector(self):
        return MockShodanConnector()

    @pytest.mark.asyncio
    async def test_fetch_known_ip(self, connector):
        """Test Shodan lookup for known IP."""
        query = ConnectorQuery(
            query_type="shodan",
            params={"ip": "8.8.8.8"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["found"] is True
        assert result.data["ip"] == "8.8.8.8"
        assert result.data["org"] == "Google LLC"
        assert 53 in result.data["ports"]

    @pytest.mark.asyncio
    async def test_fetch_cloudflare_ip(self, connector):
        """Test Shodan lookup for Cloudflare IP."""
        query = ConnectorQuery(
            query_type="shodan",
            params={"ip": "1.1.1.1"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["found"] is True
        assert result.data["org"] == "Cloudflare, Inc."
        assert 443 in result.data["ports"]

    @pytest.mark.asyncio
    async def test_fetch_unknown_ip(self, connector):
        """Test Shodan lookup for unknown IP."""
        query = ConnectorQuery(
            query_type="shodan",
            params={"ip": "192.168.1.1"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_known_domain(self, connector):
        """Test Shodan lookup for known domain."""
        query = ConnectorQuery(
            query_type="shodan",
            params={"domain": "google.com"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["found"] is True
        assert result.data["domain"] == "google.com"
        assert "www" in result.data["subdomains"]

    @pytest.mark.asyncio
    async def test_fetch_unknown_domain(self, connector):
        """Test Shodan lookup for unknown domain."""
        query = ConnectorQuery(
            query_type="shodan",
            params={"domain": "unknown-domain-12345.com"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["found"] is False

    @pytest.mark.asyncio
    async def test_fetch_no_params(self, connector):
        """Test Shodan lookup without parameters."""
        query = ConnectorQuery(
            query_type="shodan",
            params={},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "parameter is required" in result.error


@pytest.mark.unit
class TestShodanConnectorGraceful:
    """Tests for ShodanConnector graceful degradation."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_skipped(self):
        """Test that missing API key returns skipped result, not error."""
        connector = ShodanConnector()

        with patch("osint_agent.config.settings") as mock_settings:
            mock_settings.shodan_api_key = ""

            query = ConnectorQuery(
                query_type="shodan",
                params={"ip": "8.8.8.8"},
            )

            result = await connector.fetch(query)

            # Should succeed (not error) because Shodan is optional
            assert result.success is True
            assert result.data["found"] is False
            assert result.data["skipped"] is True
            assert "not configured" in result.data["reason"]
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_no_api_key_logs_info(self):
        """Test that missing API key logs info message."""
        connector = ShodanConnector()

        with patch("osint_agent.config.settings") as mock_settings:
            mock_settings.shodan_api_key = ""

            query = ConnectorQuery(
                query_type="shodan",
                params={"ip": "8.8.8.8"},
            )

            with patch("osint_agent.connectors.shodan.logger") as mock_logger:
                await connector.fetch(query)

                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                assert call_args[0][0] == "shodan_skipped"
                assert call_args[1]["reason"] == "API key not configured"


@pytest.mark.unit
class TestShodanAnalyzer:
    """Tests for ShodanAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        return ShodanAnalyzer()

    def test_analyze_ip_with_vulns(self, analyzer):
        """Test Red Flag for IP with vulnerabilities."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": ["CVE-2021-44228", "CVE-2021-45046"],
            "ports": [80, 443],
            "domains": ["example.com"],
        }

        flags = analyzer.analyze_ip(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_VULNS_FOUND" in flag_ids

        vuln_flag = next(f for f in flags if f.id == "SHODAN_VULNS_FOUND")
        assert vuln_flag.priority == RedFlagPriority.HIGH

    def test_analyze_ip_many_ports(self, analyzer):
        """Test Red Flag for IP with many open ports."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": list(range(1, 30)),  # 29 ports
            "domains": ["example.com"],
        }

        flags = analyzer.analyze_ip(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_MANY_PORTS" in flag_ids

    def test_analyze_ip_suspicious_ports(self, analyzer):
        """Test Red Flag for suspicious ports."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": [21, 23, 6379, 27017],  # FTP, Telnet, Redis, MongoDB
            "domains": ["example.com"],
        }

        flags = analyzer.analyze_ip(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_SUSPICIOUS_PORT_21" in flag_ids  # FTP
        assert "SHODAN_SUSPICIOUS_PORT_23" in flag_ids  # Telnet
        assert "SHODAN_SUSPICIOUS_PORT_6379" in flag_ids  # Redis
        assert "SHODAN_SUSPICIOUS_PORT_27017" in flag_ids  # MongoDB

    def test_analyze_ip_shared_hosting(self, analyzer):
        """Test Red Flag for shared hosting."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": [80, 443],
            "domains": [f"site{i}.com" for i in range(20)],  # 20 domains
        }

        flags = analyzer.analyze_ip(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_SHARED_HOSTING" in flag_ids

    def test_analyze_ip_clean(self, analyzer):
        """Test no Red Flags for clean IP."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": [80, 443],
            "domains": ["example.com"],
        }

        flags = analyzer.analyze_ip(shodan_data)

        assert len(flags) == 0

    def test_analyze_ip_not_found(self, analyzer):
        """Test no Red Flags for IP not found."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": False,
        }

        flags = analyzer.analyze_ip(shodan_data)

        assert len(flags) == 0

    def test_analyze_domain_many_subdomains(self, analyzer):
        """Test Red Flag for domain with many subdomains."""
        shodan_data = {
            "domain": "example.com",
            "found": True,
            "subdomains": [f"sub{i}" for i in range(60)],
        }

        flags = analyzer.analyze_domain(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_MANY_SUBDOMAINS" in flag_ids

    def test_analyze_domain_clean(self, analyzer):
        """Test no Red Flags for clean domain."""
        shodan_data = {
            "domain": "example.com",
            "found": True,
            "subdomains": ["www", "mail"],
        }

        flags = analyzer.analyze_domain(shodan_data)

        assert len(flags) == 0
