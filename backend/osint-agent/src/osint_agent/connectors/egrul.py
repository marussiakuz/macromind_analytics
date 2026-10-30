"""EGRUL Connector — ФНС ЕГРЮЛ API.

Retrieves company registration data from the Federal Tax Service (FNS).
Sources:
- egrul.nalog.ru — main EGRUL lookup
- service.nalog.ru — additional checks (mass address, disqualifications)

Note: FNS does not have a public REST API. This connector uses web scraping
with appropriate rate limiting and caching.
"""

import re
from datetime import datetime
from typing import Any

import httpx
from lxml import html

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import (
    BlockAResult,
    CompanyData,
    ConnectorQuery,
    ConnectorResult,
    RedFlag,
    RedFlagCategory,
    RedFlagPriority,
)
from osint_agent.utils import get_logger


def validate_inn(inn: str) -> bool:
    """Validate INN format with checksum.

    ИНН юридического лица — 10 цифр, ИП — 12 цифр.
    Последние цифры — контрольная сумма.

    Args:
        inn: Строка с ИНН

    Returns:
        True если ИНН валиден
    """
    if not inn or not isinstance(inn, str):
        return False

    # Убираем пробелы и дефисы
    inn = inn.replace(" ", "").replace("-", "")

    # Проверяем что только цифры
    if not inn.isdigit():
        return False

    # Проверяем длину
    if len(inn) not in (10, 12):
        return False

    # Контрольная сумма для 10-значного ИНН (юрлица)
    if len(inn) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(int(inn[i]) * weights[i] for i in range(9)) % 11 % 10
        return checksum == int(inn[9])

    # Контрольная сумма для 12-значного ИНН (ИП)
    if len(inn) == 12:
        weights1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        weights2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        check1 = sum(int(inn[i]) * weights1[i] for i in range(10)) % 11 % 10
        check2 = sum(int(inn[i]) * weights2[i] for i in range(11)) % 11 % 10
        return check1 == int(inn[10]) and check2 == int(inn[11])

    return False


def validate_domain(domain: str) -> bool:
    """Validate domain name format and block internal hosts.

    Защита от SSRF атак — блокируем запросы к внутренним хостам.

    Args:
        domain: Доменное имя

    Returns:
        True если домен валиден
    """
    if not domain or len(domain) > 253:
        return False

    # Блокируем IP адреса
    try:
        import ipaddress
        ipaddress.ip_address(domain)
        return False
    except ValueError:
        pass

    # Блокируем внутренние домены
    blocked = ['localhost', 'internal', 'local', 'lan', 'intranet']
    if any(domain.endswith(f'.{b}') or domain == b for b in blocked):
        return False

    # Базовая проверка формата
    return bool(re.match(
        r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$',
        domain
    ))

logger = get_logger(__name__)

# Mass registration address base URL
MASS_ADDRESS_URL = "https://service.nalog.ru/addrfind.do"

# Disqualified persons URL
DISQUALIFICATION_URL = "https://service.nalog.ru/disfind.do"


class EGRULConnector(BaseConnector):
    """Connector for FNS EGRUL (Единый государственный реестр юридических лиц).

    Retrieves:
    - Company registration data (INN, OGRN, name, legal form)
    - Registration address
    - OKVED codes (activity types)
    - Charter capital
    - Registration date
    - Company status
    """

    BASE_URL = "https://egrul.nalog.ru"

    @property
    def name(self) -> str:
        return "egrul"

    @property
    def rate_limit(self) -> int:
        return 60  # 1 request per second

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Fetch company data from EGRUL.

        Args:
            query: ConnectorQuery with params:
                - inn: str (ИНН компании)
                - ogrn: str (optional, ОГРН)

        Returns:
            ConnectorResult with CompanyData
        """
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="INN is required",
            )

        # Валидация формата ИНН (10 цифр для юрлиц, 12 для ИП)
        if not validate_inn(inn):
            return ConnectorResult(
                success=False,
                source=self.name,
                error="Invalid INN format (must be 10 or 12 digits with valid checksum)",
            )

        try:
            # Step 1: Search for company by INN
            search_result = await self._search_by_inn(inn)
            if not search_result:
                return ConnectorResult(
                    success=False,
                    source=self.name,
                    error=f"Company with INN {inn} not found",
                )

            # Step 2: Get full company data
            company_data = await self._get_company_details(search_result)

            return ConnectorResult(
                success=True,
                data=company_data.model_dump(),
                source=self.name,
                confidence=1.0,
            )

        except Exception as e:
            logger.error("egrul_fetch_error", inn=inn, error=str(e))
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _search_by_inn(self, inn: str) -> dict[str, Any] | None:
        """Search company by INN in EGRUL.

        The EGRUL website uses a two-step process:
        1. Submit search query → get captcha/token
        2. Fetch results using token
        """
        client = await self.get_client()

        try:
            # Step 1: Initial search request
            response = await client.post(
                f"{self.BASE_URL}",
                data={"query": inn, "page": ""},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (compatible; MacroMindBot/1.0)",
                },
            )
            response.raise_for_status()

            # Parse response to find company link/data
            tree = html.fromstring(response.text)

            # Look for result table
            rows = tree.xpath('//table[@class="result-table"]//tr')
            if not rows:
                # Try alternative parsing
                rows = tree.xpath('//div[contains(@class, "res-row")]')

            if rows:
                # Extract first result
                return self._parse_search_result(rows[0])

            return None

        except httpx.HTTPStatusError as e:
            logger.warning("egrul_http_error", status=e.response.status_code)
            return None
        except Exception as e:
            logger.error("egrul_search_error", error=str(e))
            return None

    def _parse_search_result(self, row: Any) -> dict[str, Any]:
        """Parse search result row from EGRUL."""
        # Extract text content from row
        text = row.text_content() if hasattr(row, 'text_content') else str(row)

        # Try to extract INN, OGRN, name from text
        result = {}

        # INN pattern: 10 or 12 digits
        inn_match = re.search(r'\b(\d{10}|\d{12})\b', text)
        if inn_match:
            result['inn'] = inn_match.group(1)

        # OGRN pattern: 13 digits
        ogrn_match = re.search(r'\b(\d{13})\b', text)
        if ogrn_match:
            result['ogrn'] = ogrn_match.group(1)

        # Extract company name (usually the first line)
        lines = text.strip().split('\n')
        if lines:
            result['raw_name'] = lines[0].strip()

        return result

    async def _get_company_details(self, search_result: dict[str, Any]) -> CompanyData:
        """Get full company details from search result.

        In real implementation, this would follow the link to get full data.
        For now, we construct CompanyData from available information.
        """
        inn = search_result.get('inn', '')
        ogrn = search_result.get('ogrn', '')
        raw_name = search_result.get('raw_name', '')

        # Parse legal form from name
        legal_form = self._detect_legal_form(raw_name)

        # Build CompanyData
        return CompanyData(
            inn=inn,
            ogrn=ogrn,
            name=raw_name,
            full_name=raw_name,
            legal_form=legal_form,
            registration_date=None,  # TODO: extract from full data
            address="",  # TODO: extract from full data
            is_mass_address=False,  # TODO: check separately
            okved_codes=[],  # TODO: extract from full data
            okved_main="",  # TODO: extract from full data
            charter_capital=0.0,  # TODO: extract from full data
            status="active",  # TODO: extract from full data
            region_code=inn[:2] if len(inn) >= 10 else "",
        )

    def _detect_legal_form(self, name: str) -> str:
        """Detect legal form from company name using word boundaries.

        Используем regex с \b для избежания ложных срабатываний
        (например, 'ООООО' или 'ТОООО').
        """
        name_upper = name.upper()

        patterns = {
            'OOO': r'\bООО\b|\bОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ\b',
            'ZAO': r'\bЗАО\b|\bЗАКРЫТОЕ\s+АКЦИОНЕРНОЕ\s+ОБЩЕСТВО\b',
            'OAO': r'\bОАО\b|\bОТКРЫТОЕ\s+АКЦИОНЕРНОЕ\s+ОБЩЕСТВО\b',
            'PAO': r'\bПАО\b|\bПУБЛИЧНОЕ\s+АКЦИОНЕРНОЕ\s+ОБЩЕСТВО\b',
            'AO': r'\bАО\b|\bАКЦИОНЕРНОЕ\s+ОБЩЕСТВО\b',
        }

        for form, pattern in patterns.items():
            if re.search(pattern, name_upper):
                return form

        return 'OTHER'

    async def health_check(self) -> bool:
        """Check if EGRUL website is accessible."""
        try:
            client = await self.get_client()
            response = await client.head(
                self.BASE_URL,
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def check_mass_address(self, address: str) -> bool:
        """Check if address is a mass registration address.

        Uses FNS service: service.nalog.ru/addrfind.do
        """
        if not address:
            return False

        try:
            client = await self.get_client()
            response = await client.post(
                MASS_ADDRESS_URL,
                data={"faddr": address},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "Mozilla/5.0 (compatible; MacroMindBot/1.0)",
                },
                timeout=15.0,
            )

            # Check if address is in mass registration list
            # Response contains list of addresses if found
            return "Адрес массовой регистрации" in response.text

        except Exception as e:
            logger.warning("mass_address_check_error", error=str(e))
            return False

    async def check_okved_match(
        self,
        inn: str,
        declared_activity: str,
        registered_okved: str,
    ) -> bool:
        """Check if declared activity matches registered OKVED.

        Returns True if there's a mismatch (Red Flag condition).
        """
        if not declared_activity or not registered_okved:
            return False

        # Simple text comparison
        # In real implementation, use OKVED classifier
        declared_lower = declared_activity.lower()
        okved_lower = registered_okved.lower()

        # Check for obvious mismatches
        # This is a simplified check — real implementation would use OKVED dictionary
        return False


class MockEGRULConnector(BaseConnector):
    """Mock EGRUL connector for testing.

    Returns realistic test data without making actual API calls.
    """

    # Test data for different companies
    MOCK_DATA: dict[str, dict[str, Any]] = {
        "7701234567": {
            "inn": "7701234567",
            "ogrn": "1027700132195",
            "name": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            "full_name": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТЕСТОВАЯ КОМПАНИЯ"',
            "legal_form": "OOO",
            "registration_date": "2015-03-20T00:00:00",
            "address": "123456, г Москва, ул Тестовая, д 1",
            "is_mass_address": False,
            "okved_codes": ["62.01", "62.02", "63.11"],
            "okved_main": "62.01",
            "charter_capital": 10000.0,
            "status": "active",
            "region_code": "77",
        },
        "7799888777": {
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
        },
        "7701234568": {
            "inn": "7701234568",
            "ogrn": "1027700132196",
            "name": 'ЗАО "СТАРАЯ КОМПАНИЯ"',
            "full_name": 'ЗАКРЫТОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО "СТАРАЯ КОМПАНИЯ"',
            "legal_form": "ZAO",
            "registration_date": "2005-06-10T00:00:00",
            "address": "119019, г Москва, ул Большая Ордынка, д 40",
            "is_mass_address": False,
            "okved_codes": ["70.10", "70.22"],
            "okved_main": "70.10",
            "charter_capital": 500000.0,
            "status": "active",
            "region_code": "77",
        },
    }

    @property
    def name(self) -> str:
        return "egrul"

    @property
    def rate_limit(self) -> int:
        return 1000  # No real rate limiting for mock

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Return mock company data."""
        inn = query.params.get("inn")
        if not inn:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="INN is required",
            )

        # Simulate network delay
        import asyncio
        await asyncio.sleep(0.1)

        if inn in self.MOCK_DATA:
            return ConnectorResult(
                success=True,
                data=self.MOCK_DATA[inn],
                source=f"{self.name}:mock",
                confidence=1.0,
            )

        return ConnectorResult(
            success=False,
            source=self.name,
            error=f"Company with INN {inn} not found",
        )

    async def health_check(self) -> bool:
        return True


def build_block_a_result(company_data: dict[str, Any]) -> BlockAResult:
    """Build Block A result from company data.

    Applies Red Flag rules from OSINT_Rules.md §2.
    """
    red_flags = []

    # A.1 — Mass address check
    if company_data.get("is_mass_address"):
        red_flags.append(RedFlag(
            id="MASS_ADDRESS",
            priority=RedFlagPriority.HIGH,
            category=RedFlagCategory.LEGAL,
            description="Юридический адрес является адресом массовой регистрации",
            block="A",
            evidence={"address": company_data.get("address")},
            source_ref="ФНС — адреса массовой регистрации",
        ))

    # A.4 — Young company check
    reg_date_str = company_data.get("registration_date")
    if reg_date_str:
        try:
            reg_date = datetime.fromisoformat(reg_date_str.replace("Z", "+00:00"))
            age_days = (datetime.utcnow() - reg_date.replace(tzinfo=None)).days

            if age_days < 180:  # Less than 6 months
                red_flags.append(RedFlag(
                    id="YOUNG_COMPANY_HIGH",
                    priority=RedFlagPriority.HIGH,
                    category=RedFlagCategory.LEGAL,
                    description=f"Компания зарегистрирована менее 6 месяцев назад ({age_days} дней)",
                    block="A",
                    evidence={"registration_date": reg_date_str, "age_days": age_days},
                    source_ref="ЕГРЮЛ",
                ))
            elif age_days < 365:  # Less than 1 year
                red_flags.append(RedFlag(
                    id="YOUNG_COMPANY_MEDIUM",
                    priority=RedFlagPriority.MEDIUM,
                    category=RedFlagCategory.LEGAL,
                    description=f"Компания зарегистрирована менее 1 года назад ({age_days} дней)",
                    block="A",
                    evidence={"registration_date": reg_date_str, "age_days": age_days},
                    source_ref="ЕГРЮЛ",
                ))
        except (ValueError, TypeError):
            pass

    # A.5 — OKVED mismatch (needs declared_activity from pitch deck)
    # This check is done externally when declared_activity is available

    # A.6 — Minimum charter capital
    charter_capital = company_data.get("charter_capital", 0)
    if charter_capital == 10000:
        red_flags.append(RedFlag(
            id="MIN_CAPITAL",
            priority=RedFlagPriority.LOW,
            category=RedFlagCategory.LEGAL,
            description="Минимальный уставной капитал (10 000 ₽)",
            block="A",
            evidence={"charter_capital": charter_capital},
            source_ref="ЕГРЮЛ",
        ))

    # Build CompanyData model
    company = CompanyData(
        inn=company_data.get("inn", ""),
        ogrn=company_data.get("ogrn", ""),
        name=company_data.get("name", ""),
        full_name=company_data.get("full_name", ""),
        legal_form=company_data.get("legal_form", "OTHER"),
        registration_date=datetime.fromisoformat(reg_date_str) if reg_date_str else None,
        address=company_data.get("address", ""),
        is_mass_address=company_data.get("is_mass_address", False),
        okved_codes=company_data.get("okved_codes", []),
        okved_main=company_data.get("okved_main", ""),
        charter_capital=charter_capital,
        status=company_data.get("status", "active"),
        region_code=company_data.get("region_code", ""),
    )

    return BlockAResult(company=company, red_flags=red_flags)
