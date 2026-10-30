"""Tests for mock connectors."""

import pytest

from osint_agent.connectors.mock import (
    MockFNSTaxConnector,
    MockKADConnector,
    MockSudrfConnector,
    MockFSSPConnector,
    MockSanctionConnector,
    MockNewsConnector,
    MockTenderConnector,
    MockPEPConnector,
    MockSocialConnector,
)
from osint_agent.models import ConnectorQuery


@pytest.mark.unit
class TestMockFNSTaxConnector:
    """Tests for MockFNSTaxConnector."""

    @pytest.fixture
    def connector(self):
        return MockFNSTaxConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_debt(self, connector):
        query = ConnectorQuery(query_type="tax_debt", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["has_tax_debt"] is True
        assert result.data["debt_amount"] == 1500000.0

    @pytest.mark.asyncio
    async def test_fetch_company_without_debt(self, connector):
        query = ConnectorQuery(query_type="tax_debt", params={"inn": "7701234567"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["has_tax_debt"] is False

    @pytest.mark.asyncio
    async def test_fetch_disqualified_director(self, connector):
        query = ConnectorQuery(query_type="tax_debt", params={"inn": "7701234569"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_disqualified_director"] is True


@pytest.mark.unit
class TestMockKADConnector:
    """Tests for MockKADConnector."""

    @pytest.fixture
    def connector(self):
        return MockKADConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_cases(self, connector):
        query = ConnectorQuery(query_type="court_cases", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 2

    @pytest.mark.asyncio
    async def test_fetch_company_without_cases(self, connector):
        query = ConnectorQuery(query_type="court_cases", params={"inn": "7701234567"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 1  # One minor case


@pytest.mark.unit
class TestMockSudrfConnector:
    """Tests for MockSudrfConnector."""

    @pytest.fixture
    def connector(self):
        return MockSudrfConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_cases(self, connector):
        query = ConnectorQuery(query_type="court_cases", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 1

    @pytest.mark.asyncio
    async def test_fetch_company_without_cases(self, connector):
        query = ConnectorQuery(query_type="court_cases", params={"inn": "7701234567"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 0


@pytest.mark.unit
class TestMockFSSPConnector:
    """Tests for MockFSSPConnector."""

    @pytest.fixture
    def connector(self):
        return MockFSSPConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_productions(self, connector):
        query = ConnectorQuery(query_type="bailiff", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 2
        assert result.data["productions"][0]["amount"] == 1500000.0

    @pytest.mark.asyncio
    async def test_fetch_company_without_productions(self, connector):
        query = ConnectorQuery(query_type="bailiff", params={"inn": "7701234567"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 0


@pytest.mark.unit
class TestMockSanctionConnector:
    """Tests for MockSanctionConnector."""

    @pytest.fixture
    def connector(self):
        return MockSanctionConnector()

    @pytest.mark.asyncio
    async def test_fetch_sanctioned_person(self, connector):
        query = ConnectorQuery(query_type="sanctions", params={"full_name": "Санкционный Петр"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_sanctioned"] is True
        assert len(result.data["matches"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_clean_person(self, connector):
        query = ConnectorQuery(query_type="sanctions", params={"full_name": "Иванов Иван Иванович"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_sanctioned"] is False

    @pytest.mark.asyncio
    async def test_fetch_unknown_person(self, connector):
        query = ConnectorQuery(query_type="sanctions", params={"full_name": "Неизвестный Человек"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_sanctioned"] is False


@pytest.mark.unit
class TestMockNewsConnector:
    """Tests for MockNewsConnector."""

    @pytest.fixture
    def connector(self):
        return MockNewsConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_negative_news(self, connector):
        query = ConnectorQuery(query_type="news", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 2
        negative = [a for a in result.data["articles"] if a["is_negative"]]
        assert len(negative) == 2

    @pytest.mark.asyncio
    async def test_fetch_company_with_positive_news(self, connector):
        query = ConnectorQuery(query_type="news", params={"inn": "7701234567"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 1
        assert result.data["articles"][0]["is_negative"] is False


@pytest.mark.unit
class TestMockTenderConnector:
    """Tests for MockTenderConnector."""

    @pytest.fixture
    def connector(self):
        return MockTenderConnector()

    @pytest.mark.asyncio
    async def test_fetch_company_with_cartel_signs(self, connector):
        query = ConnectorQuery(query_type="tenders", params={"inn": "7799888777"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["single_source_percent"] == 100.0
        assert result.data["in_ndr"] is True

    @pytest.mark.asyncio
    async def test_fetch_company_without_tenders(self, connector):
        query = ConnectorQuery(query_type="tenders", params={"inn": "9999999999"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 0


@pytest.mark.unit
class TestMockPEPConnector:
    """Tests for MockPEPConnector."""

    @pytest.fixture
    def connector(self):
        return MockPEPConnector()

    @pytest.mark.asyncio
    async def test_fetch_pep_person(self, connector):
        query = ConnectorQuery(query_type="pep", params={"full_name": "Политиков Петр Петрович"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_pep"] is True

    @pytest.mark.asyncio
    async def test_fetch_non_pep_person(self, connector):
        query = ConnectorQuery(query_type="pep", params={"full_name": "Иванов Иван Иванович"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["is_pep"] is False


@pytest.mark.unit
class TestMockSocialConnector:
    """Tests for MockSocialConnector."""

    @pytest.fixture
    def connector(self):
        return MockSocialConnector()

    @pytest.mark.asyncio
    async def test_fetch_person_with_profiles(self, connector):
        query = ConnectorQuery(query_type="social", params={"full_name": "Иванов Иван Иванович"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 2
        platforms = [p["platform"] for p in result.data["profiles"]]
        assert "vk" in platforms
        assert "linkedin" in platforms

    @pytest.mark.asyncio
    async def test_fetch_person_without_profiles(self, connector):
        query = ConnectorQuery(query_type="social", params={"full_name": "Неизвестный Человек"})
        result = await connector.fetch(query)
        assert result.success is True
        assert result.data["total"] == 0
