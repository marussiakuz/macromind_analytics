"""Tests for EGRUL Connector."""

import pytest
from datetime import datetime, timedelta

from osint_agent.connectors.egrul import (
    EGRULConnector,
    MockEGRULConnector,
    build_block_a_result,
)
from osint_agent.models import ConnectorQuery, RedFlagPriority


@pytest.mark.unit
class TestMockEGRULConnector:
    """Tests for MockEGRULConnector."""

    @pytest.fixture
    def connector(self):
        return MockEGRULConnector()

    @pytest.mark.asyncio
    async def test_fetch_existing_company(self, connector):
        """Test fetching existing company by INN."""
        query = ConnectorQuery(
            query_type="company_legal",
            params={"inn": "7701234567"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["inn"] == "7701234567"
        assert result.data["name"] == 'ООО "ТЕСТОВАЯ КОМПАНИЯ"'
        assert result.data["legal_form"] == "OOO"
        assert result.source.endswith(":mock")

    @pytest.mark.asyncio
    async def test_fetch_nonexistent_company(self, connector):
        """Test fetching non-existent company."""
        query = ConnectorQuery(
            query_type="company_legal",
            params={"inn": "9999999999"},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_fetch_without_inn(self, connector):
        """Test fetching without INN."""
        query = ConnectorQuery(
            query_type="company_legal",
            params={},
        )

        result = await connector.fetch(query)

        assert result.success is False
        assert "INN is required" in result.error

    @pytest.mark.asyncio
    async def test_fetch_zao_company(self, connector):
        """Test fetching ZAO company."""
        query = ConnectorQuery(
            query_type="company_legal",
            params={"inn": "7701234568"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["legal_form"] == "ZAO"

    @pytest.mark.asyncio
    async def test_fetch_mass_address_company(self, connector):
        """Test fetching company with mass address."""
        query = ConnectorQuery(
            query_type="company_legal",
            params={"inn": "7799888777"},
        )

        result = await connector.fetch(query)

        assert result.success is True
        assert result.data["is_mass_address"] is True

    @pytest.mark.asyncio
    async def test_health_check(self, connector):
        """Test health check."""
        assert await connector.health_check() is True


@pytest.mark.unit
class TestBuildBlockAResult:
    """Tests for build_block_a_result function."""

    def test_build_normal_company(self):
        """Test building result for normal company."""
        data = {
            "inn": "7701234567",
            "ogrn": "1027700132195",
            "name": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЕСТОВАЯ КОМПАНИЯ"',
            "legal_form": "OOO",
            "registration_date": "2020-01-15T00:00:00",
            "address": "123456, г Москва, ул Тестовая, д 1",
            "is_mass_address": False,
            "okved_codes": ["62.01"],
            "okved_main": "62.01",
            "charter_capital": 100000.0,
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        assert result.company.inn == "7701234567"
        assert result.company.legal_form == "OOO"
        assert len(result.red_flags) == 0

    def test_build_mass_address_company(self):
        """Test building result for company with mass address."""
        data = {
            "inn": "7799888777",
            "ogrn": "1037700000000",
            "name": 'ООО "МАССОВЫЙ АДРЕС"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МАССОВЫЙ АДРЕС"',
            "legal_form": "OOO",
            "registration_date": "2020-01-15T00:00:00",
            "address": "101000, г Москва, ул Мясницкая, д 15",
            "is_mass_address": True,
            "okved_codes": ["47.11"],
            "okved_main": "47.11",
            "charter_capital": 10000.0,
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        # Should have MASS_ADDRESS and MIN_CAPITAL flags
        flag_ids = [f.id for f in result.red_flags]
        assert "MASS_ADDRESS" in flag_ids
        assert "MIN_CAPITAL" in flag_ids

        # Check MASS_ADDRESS priority
        mass_flag = next(f for f in result.red_flags if f.id == "MASS_ADDRESS")
        assert mass_flag.priority == RedFlagPriority.HIGH

    def test_build_young_company_high(self):
        """Test building result for very young company (< 6 months)."""
        # Company registered 30 days ago
        reg_date = (datetime.utcnow() - timedelta(days=30)).isoformat()

        data = {
            "inn": "7701234567",
            "ogrn": "1027700132195",
            "name": 'ООО "МОЛОДАЯ КОМПАНИЯ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МОЛОДАЯ КОМПАНИЯ"',
            "legal_form": "OOO",
            "registration_date": reg_date,
            "address": "123456, г Москва, ул Тестовая, д 1",
            "is_mass_address": False,
            "okved_codes": ["62.01"],
            "okved_main": "62.01",
            "charter_capital": 100000.0,
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        flag_ids = [f.id for f in result.red_flags]
        assert "YOUNG_COMPANY_HIGH" in flag_ids

        young_flag = next(f for f in result.red_flags if f.id == "YOUNG_COMPANY_HIGH")
        assert young_flag.priority == RedFlagPriority.HIGH

    def test_build_young_company_medium(self):
        """Test building result for young company (6-12 months)."""
        # Company registered 200 days ago
        reg_date = (datetime.utcnow() - timedelta(days=200)).isoformat()

        data = {
            "inn": "7701234567",
            "ogrn": "1027700132195",
            "name": 'ООО "МОЛОДАЯ КОМПАНИЯ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МОЛОДАЯ КОМПАНИЯ"',
            "legal_form": "OOO",
            "registration_date": reg_date,
            "address": "123456, г Москва, ул Тестовая, д 1",
            "is_mass_address": False,
            "okved_codes": ["62.01"],
            "okved_main": "62.01",
            "charter_capital": 100000.0,
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        flag_ids = [f.id for f in result.red_flags]
        assert "YOUNG_COMPANY_MEDIUM" in flag_ids

        young_flag = next(f for f in result.red_flags if f.id == "YOUNG_COMPANY_MEDIUM")
        assert young_flag.priority == RedFlagPriority.MEDIUM

    def test_build_min_capital_company(self):
        """Test building result for company with minimum capital."""
        data = {
            "inn": "7701234567",
            "ogrn": "1027700132195",
            "name": 'ООО "МИНИМАЛЬНЫЙ КАПИТАЛ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "МИНИМАЛЬНЫЙ КАПИТАЛ"',
            "legal_form": "OOO",
            "registration_date": "2020-01-15T00:00:00",
            "address": "123456, г Москва, ул Тестовая, д 1",
            "is_mass_address": False,
            "okved_codes": ["62.01"],
            "okved_main": "62.01",
            "charter_capital": 10000.0,  # Minimum
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        flag_ids = [f.id for f in result.red_flags]
        assert "MIN_CAPITAL" in flag_ids

        min_flag = next(f for f in result.red_flags if f.id == "MIN_CAPITAL")
        assert min_flag.priority == RedFlagPriority.LOW

    def test_build_multiple_flags(self):
        """Test building result with multiple red flags."""
        # Company with mass address, minimum capital, and young age
        reg_date = (datetime.utcnow() - timedelta(days=30)).isoformat()

        data = {
            "inn": "7799888777",
            "ogrn": "1037700000000",
            "name": 'ООО "ПРОБЛЕМНАЯ КОМПАНИЯ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРОБЛЕМНАЯ КОМПАНИЯ"',
            "legal_form": "OOO",
            "registration_date": reg_date,
            "address": "101000, г Москва, ул Мясницкая, д 15",
            "is_mass_address": True,
            "okved_codes": ["47.11"],
            "okved_main": "47.11",
            "charter_capital": 10000.0,
            "status": "active",
            "region_code": "77",
        }

        result = build_block_a_result(data)

        flag_ids = [f.id for f in result.red_flags]
        assert "MASS_ADDRESS" in flag_ids
        assert "YOUNG_COMPANY_HIGH" in flag_ids
        assert "MIN_CAPITAL" in flag_ids
        assert len(result.red_flags) == 3

    def test_detect_legal_forms(self):
        """Test legal form detection from company names."""
        connector = EGRULConnector()

        assert connector._detect_legal_form('ООО "Тест"') == "OOO"
        assert connector._detect_legal_form('ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "Тест"') == "OOO"
        assert connector._detect_legal_form('ЗАО "Тест"') == "ZAO"
        assert connector._detect_legal_form('ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО "Тест"') == "ZAO"
        assert connector._detect_legal_form('ОАО "Тест"') == "OAO"
        assert connector._detect_legal_form('ПАО "Тест"') == "PAO"
        assert connector._detect_legal_form('АО "Тест"') == "AO"
        assert connector._detect_legal_form('ИП Иванов') == "OTHER"
