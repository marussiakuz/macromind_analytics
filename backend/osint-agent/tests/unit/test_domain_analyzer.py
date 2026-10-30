"""Tests for Domain Analyzer."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from osint_agent.analysis.domain import DomainAnalyzer, DomainResult, CompanyDomainAnalysis
from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.models import ConnectorResult, RedFlagPriority


@pytest.mark.unit
class TestDomainResult:
    """Tests for DomainResult."""

    def test_creation(self):
        """Test DomainResult creation."""
        result = DomainResult(domain="example.com")

        assert result.domain == "example.com"
        assert result.whois == {}
        assert result.dns == {}
        assert result.shodan == {}
        assert result.red_flags == []

    def test_to_dict(self):
        """Test DomainResult serialization."""
        result = DomainResult(
            domain="example.com",
            whois_data={"registrar": "Test Registrar"},
            dns_data={"records": {"A": ["1.2.3.4"]}},
        )

        data = result.to_dict()

        assert data["domain"] == "example.com"
        assert data["whois"]["registrar"] == "Test Registrar"
        assert data["dns"]["records"]["A"] == ["1.2.3.4"]


@pytest.mark.unit
class TestCompanyDomainAnalysis:
    """Tests for CompanyDomainAnalysis."""

    def test_creation(self):
        """Test CompanyDomainAnalysis creation."""
        analysis = CompanyDomainAnalysis(
            company_name="Test Company",
            inn="7701234567",
        )

        assert analysis.company_name == "Test Company"
        assert analysis.inn == "7701234567"
        assert analysis.domains == []
        assert analysis.connections == []
        assert analysis.red_flags == []

    def test_to_dict(self):
        """Test CompanyDomainAnalysis serialization."""
        analysis = CompanyDomainAnalysis(
            company_name="Test Company",
            inn="7701234567",
            domains=[DomainResult(domain="example.com")],
            connections=[{"from": "a.com", "to": "b.com", "type": "same_ip", "value": "1.2.3.4"}],
        )

        data = analysis.to_dict()

        assert data["company_name"] == "Test Company"
        assert len(data["domains"]) == 1
        assert len(data["connections"]) == 1


@pytest.mark.unit
class TestDomainAnalyzer:
    """Tests for DomainAnalyzer."""

    @pytest.fixture
    def mock_hub(self):
        """Create mock DataConnectorHub."""
        hub = AsyncMock(spec=DataConnectorHub)
        return hub

    @pytest.fixture
    def analyzer(self, mock_hub):
        """Create DomainAnalyzer with mock hub."""
        return DomainAnalyzer(mock_hub)

    @pytest.mark.asyncio
    async def test_analyze_company_no_website(self, analyzer, mock_hub):
        """Test analyze_company without website."""
        # Mock hub to return empty results
        mock_hub.fetch = AsyncMock(return_value=ConnectorResult(
            success=False,
            source="test",
            error="Not found",
        ))

        result = await analyzer.analyze_company(
            company_name="Test Company",
            inn="7701234567",
        )

        assert result.company_name == "Test Company"
        assert result.inn == "7701234567"
        assert result.domains == []

    @pytest.mark.asyncio
    async def test_analyze_company_with_website(self, analyzer, mock_hub):
        """Test analyze_company with website."""
        # Mock hub responses
        async def mock_fetch(query_type, params):
            if query_type == "whois":
                return ConnectorResult(
                    success=True,
                    data={
                        "domain": "example.com",
                        "registrar": "Test Registrar",
                        "creation_date": "2020-01-01T00:00:00",
                        "is_private_registration": False,
                    },
                    source="whois",
                )
            elif query_type == "dns":
                return ConnectorResult(
                    success=True,
                    data={
                        "domain": "example.com",
                        "records": {
                            "A": ["93.184.216.34"],
                            "MX": ["10 mail.example.com."],
                            "TXT": ["v=spf1 include:_spf.google.com ~all"],
                        },
                        "analysis": {
                            "has_spf": True,
                            "has_dmarc": False,
                            "mail_provider": "google",
                        },
                    },
                    source="dns",
                )
            elif query_type == "shodan":
                return ConnectorResult(
                    success=True,
                    data={
                        "ip": "93.184.216.34",
                        "found": True,
                        "org": "Example Inc.",
                        "country_name": "United States",
                        "ports": [80, 443],
                        "vulns": [],
                    },
                    source="shodan",
                )
            return ConnectorResult(success=False, source="test", error="Unknown")

        mock_hub.fetch = AsyncMock(side_effect=mock_fetch)

        result = await analyzer.analyze_company(
            company_name="Test Company",
            inn="7701234567",
            website="https://example.com",
        )

        assert result.company_name == "Test Company"
        assert len(result.domains) == 1
        assert result.domains[0].domain == "example.com"
        assert result.domains[0].whois["registrar"] == "Test Registrar"

    @pytest.mark.asyncio
    async def test_analyze_single_domain(self, analyzer, mock_hub):
        """Test _analyze_single_domain."""
        async def mock_fetch(query_type, params):
            if query_type == "whois":
                return ConnectorResult(
                    success=True,
                    data={"domain": "test.com", "is_private_registration": True},
                    source="whois",
                )
            elif query_type == "dns":
                return ConnectorResult(
                    success=True,
                    data={
                        "domain": "test.com",
                        "records": {"A": ["1.2.3.4"]},
                        "analysis": {"has_spf": False},
                    },
                    source="dns",
                )
            elif query_type == "shodan":
                return ConnectorResult(
                    success=True,
                    data={"ip": "1.2.3.4", "found": False},
                    source="shodan",
                )
            return ConnectorResult(success=False, source="test", error="Unknown")

        mock_hub.fetch = AsyncMock(side_effect=mock_fetch)

        result = await analyzer._analyze_single_domain("test.com")

        assert result.domain == "test.com"
        assert result.whois["is_private_registration"] is True
        assert len(result.red_flags) > 0

    def test_analyze_whois_flags_private_registration(self, analyzer):
        """Test WHOIS Red Flags for private registration."""
        whois_data = {
            "domain": "test.com",
            "is_private_registration": True,
        }

        flags = analyzer._analyze_whois_flags(whois_data)

        flag_ids = [f.id for f in flags]
        assert "DOMAIN_PRIVATE_REGISTRATION" in flag_ids

    def test_analyze_whois_flags_recently_registered(self, analyzer):
        """Test WHOIS Red Flags for recently registered domain."""
        from datetime import datetime, timedelta

        whois_data = {
            "domain": "test.com",
            "creation_date": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "is_private_registration": False,
        }

        flags = analyzer._analyze_whois_flags(whois_data)

        flag_ids = [f.id for f in flags]
        assert "DOMAIN_RECENTLY_REGISTERED" in flag_ids

    def test_analyze_whois_flags_expiring_soon(self, analyzer):
        """Test WHOIS Red Flags for domain expiring soon."""
        from datetime import datetime, timedelta

        whois_data = {
            "domain": "test.com",
            "expiration_date": (datetime.utcnow() + timedelta(days=15)).isoformat(),
            "is_private_registration": False,
        }

        flags = analyzer._analyze_whois_flags(whois_data)

        flag_ids = [f.id for f in flags]
        assert "DOMAIN_EXPIRING_SOON" in flag_ids

    def test_analyze_whois_flags_clean(self, analyzer):
        """Test WHOIS Red Flags for clean domain."""
        from datetime import datetime, timedelta

        whois_data = {
            "domain": "test.com",
            "creation_date": (datetime.utcnow() - timedelta(days=1000)).isoformat(),
            "expiration_date": (datetime.utcnow() + timedelta(days=365)).isoformat(),
            "is_private_registration": False,
        }

        flags = analyzer._analyze_whois_flags(whois_data)

        assert len(flags) == 0

    def test_analyze_dns_flags_no_spf(self, analyzer):
        """Test DNS Red Flags for no SPF."""
        dns_data = {
            "domain": "test.com",
            "records": {"TXT": []},
            "analysis": {"has_spf": False},
        }

        flags = analyzer._analyze_dns_flags(dns_data)

        flag_ids = [f.id for f in flags]
        assert "DNS_NO_SPF" in flag_ids

    def test_analyze_dns_flags_no_dmarc(self, analyzer):
        """Test DNS Red Flags for no DMARC."""
        dns_data = {
            "domain": "test.com",
            "records": {"TXT": ["v=spf1 include:_spf.google.com ~all"]},
            "analysis": {"has_spf": True},
        }

        flags = analyzer._analyze_dns_flags(dns_data)

        flag_ids = [f.id for f in flags]
        assert "DNS_NO_DMARC" in flag_ids

    def test_analyze_dns_flags_clean(self, analyzer):
        """Test DNS Red Flags for clean domain."""
        dns_data = {
            "domain": "test.com",
            "records": {
                "TXT": [
                    "v=spf1 include:_spf.google.com ~all",
                    "v=DMARC1; p=none",
                ],
            },
            "analysis": {"has_spf": True},
        }

        flags = analyzer._analyze_dns_flags(dns_data)

        assert len(flags) == 0

    def test_analyze_shodan_flags_vulns(self, analyzer):
        """Test Shodan Red Flags for vulnerabilities."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": ["CVE-2021-44228"],
            "ports": [80, 443],
        }

        flags = analyzer._analyze_shodan_flags(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_VULNS_FOUND" in flag_ids

    def test_analyze_shodan_flags_many_ports(self, analyzer):
        """Test Shodan Red Flags for many ports."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": list(range(1, 25)),
        }

        flags = analyzer._analyze_shodan_flags(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_MANY_PORTS" in flag_ids

    def test_analyze_shodan_flags_suspicious_ports(self, analyzer):
        """Test Shodan Red Flags for suspicious ports."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": True,
            "vulns": [],
            "ports": [21, 23, 6379],
        }

        flags = analyzer._analyze_shodan_flags(shodan_data)

        flag_ids = [f.id for f in flags]
        assert "SHODAN_SUSPICIOUS_PORT_21" in flag_ids
        assert "SHODAN_SUSPICIOUS_PORT_23" in flag_ids
        assert "SHODAN_SUSPICIOUS_PORT_6379" in flag_ids

    def test_analyze_shodan_flags_not_found(self, analyzer):
        """Test Shodan Red Flags when IP not found."""
        shodan_data = {
            "ip": "1.2.3.4",
            "found": False,
        }

        flags = analyzer._analyze_shodan_flags(shodan_data)

        assert len(flags) == 0

    def test_find_domain_connections_same_ip(self, analyzer):
        """Test finding domains on same IP."""
        domain_results = [
            DomainResult(
                domain="site1.com",
                dns_data={"records": {"A": ["1.2.3.4"]}},
            ),
            DomainResult(
                domain="site2.com",
                dns_data={"records": {"A": ["1.2.3.4"]}},
            ),
            DomainResult(
                domain="site3.com",
                dns_data={"records": {"A": ["5.6.7.8"]}},
            ),
        ]

        connections = analyzer._find_domain_connections(domain_results)

        assert len(connections) == 1
        assert connections[0]["type"] == "same_ip"
        assert connections[0]["value"] == "1.2.3.4"

    def test_find_domain_connections_same_ns(self, analyzer):
        """Test finding domains with same nameserver."""
        domain_results = [
            DomainResult(
                domain="site1.com",
                dns_data={"records": {"NS": ["ns1.host.com."]}},
            ),
            DomainResult(
                domain="site2.com",
                dns_data={"records": {"NS": ["ns1.host.com."]}},
            ),
        ]

        connections = analyzer._find_domain_connections(domain_results)

        assert len(connections) == 1
        assert connections[0]["type"] == "same_nameserver"

    def test_find_domain_connections_same_mx(self, analyzer):
        """Test finding domains with same mail server."""
        domain_results = [
            DomainResult(
                domain="site1.com",
                dns_data={"records": {"MX": ["10 mx.google.com."]}},
            ),
            DomainResult(
                domain="site2.com",
                dns_data={"records": {"MX": ["10 mx.google.com."]}},
            ),
        ]

        connections = analyzer._find_domain_connections(domain_results)

        assert len(connections) == 1
        assert connections[0]["type"] == "same_mail_server"

    def test_find_domain_connections_no_connections(self, analyzer):
        """Test no connections found."""
        domain_results = [
            DomainResult(
                domain="site1.com",
                dns_data={"records": {"A": ["1.2.3.4"], "NS": ["ns1.a.com."], "MX": ["10 mx.a.com."]}},
            ),
            DomainResult(
                domain="site2.com",
                dns_data={"records": {"A": ["5.6.7.8"], "NS": ["ns1.b.com."], "MX": ["10 mx.b.com."]}},
            ),
        ]

        connections = analyzer._find_domain_connections(domain_results)

        assert len(connections) == 0

    def test_prepare_llm_context(self, analyzer):
        """Test LLM context preparation."""
        analysis = CompanyDomainAnalysis(
            company_name="Test Company",
            inn="7701234567",
            domains=[
                DomainResult(
                    domain="example.com",
                    whois_data={
                        "registrar": "Test Registrar",
                        "creation_date": "2020-01-01",
                        "is_private_registration": False,
                    },
                    dns_data={
                        "records": {"A": ["1.2.3.4"], "MX": ["10 mx.example.com."]},
                        "analysis": {"mail_provider": "google"},
                    },
                    shodan_data={
                        "found": True,
                        "org": "Example Inc.",
                        "country_name": "US",
                        "ports": [80, 443],
                        "vulns": [],
                    },
                ),
            ],
            connections=[
                {"from": "a.com", "to": "b.com", "type": "same_ip", "value": "1.2.3.4"},
            ],
            red_flags=[],
        )

        context = analyzer.prepare_llm_context(analysis)

        assert "Test Company" in context
        assert "7701234567" in context
        assert "example.com" in context
        assert "Test Registrar" in context
        assert "1.2.3.4" in context
        assert "same_ip" in context
