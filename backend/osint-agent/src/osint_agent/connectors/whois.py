"""WHOIS Connector — получение регистрационных данных доменов.

Источники:
- python-whois — стандартные WHOIS запросы
- DomainTools — расширенный WHOIS (опционально, платно)
- WHOXY — исторические данные (опционально, платно)

ВАЖНО (152-ФЗ):
- WHOIS данные могут содержать персональные данные (имя, email владельца)
- Если данные скрыты за приватной регистрацией — НЕ пытаемся обойти
- Хранение WHOIS данных — только в РФ, с ограничением по времени
"""

from datetime import datetime
from typing import Any

import whois as python_whois

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult
from osint_agent.utils import get_logger

logger = get_logger(__name__)


class WhoisConnector(BaseConnector):
    """WHOIS запросы к доменам.

    Получает:
    - registrar — регистратор домена
    - creation_date — дата регистрации
    - expiration_date — дата окончания
    - name_servers — серверы имен
    - registrant_name — имя владельца (может быть скрыто)
    - registrant_org — организация владельца
    - registrant_country — страна
    - emails — email-адреса (могут быть скрыты)
    - dnssec — наличие DNSSEC

    Ограничения (152-ФЗ):
    - Если данные владельца скрыты за приватной регистрацией — возвращаем None
    - Не пытаемся обойти приватную регистрацию
    - Не храним персональные данные дольше необходимого
    """

    @property
    def name(self) -> str:
        return "whois"

    @property
    def rate_limit(self) -> int:
        return 60  # 1 запрос в секунду

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        """Получить WHOIS данные домена.

        Args:
            query: ConnectorQuery с params:
                - domain: str (доменное имя, например "ya.ru")

        Returns:
            ConnectorResult с WHOIS данными
        """
        domain = query.params.get("domain")
        if not domain:
            return ConnectorResult(
                success=False,
                source=self.name,
                error="Domain is required",
            )

        try:
            # Выполняем WHOIS запрос
            whois_data = await self._whois_lookup(domain)

            # Проверяем, не скрыты ли данные (приватная регистрация)
            is_private = self._check_private_registration(whois_data)

            # Формируем результат
            result_data = self._format_result(domain, whois_data, is_private)

            return ConnectorResult(
                success=True,
                data=result_data,
                source=self.name,
                confidence=0.9 if not is_private else 0.5,
            )

        except Exception as e:
            logger.error("whois_error", domain=domain, error=str(e))
            return ConnectorResult(
                success=False,
                source=self.name,
                error=str(e),
            )

    async def _whois_lookup(self, domain: str) -> dict[str, Any]:
        """Выполнить WHOIS запрос."""
        # python-whois — синхронная библиотека, оборачиваем
        # Используем asyncio.to_thread() (Python 3.9+) вместо устаревшего get_event_loop()
        import asyncio

        w = await asyncio.to_thread(python_whois.whois, domain)

        return {
            "registrar": w.registrar,
            "creation_date": self._normalize_date(w.creation_date),
            "expiration_date": self._normalize_date(w.expiration_date),
            "last_updated": self._normalize_date(w.last_updated),
            "name_servers": list(w.name_servers) if w.name_servers else [],
            "registrant_name": w.name,
            "registrant_org": w.org,
            "registrant_country": w.country,
            "registrant_state": w.state,
            "registrant_city": w.city,
            "emails": self._normalize_emails(w.emails),
            "dnssec": w.dnssec,
            "status": w.status,
        }

    def _normalize_date(self, date: Any) -> str | None:
        """Нормализовать дату WHOIS в ISO формат."""
        if date is None:
            return None

        if isinstance(date, list):
            date = date[0] if date else None

        if isinstance(date, datetime):
            return date.isoformat()

        return str(date) if date else None

    def _normalize_emails(self, emails: Any) -> list[str]:
        """Нормализовать email-адреса."""
        if emails is None:
            return []

        if isinstance(emails, str):
            return [emails]

        if isinstance(emails, list):
            return [str(e) for e in emails if e]

        return []

    def _check_private_registration(self, whois_data: dict) -> bool:
        """Проверить, используется ли приватная регистрация.

        Признаки приватной регистрации:
        - WhoisGuard, Privacy Protect, Private Registration в имени/организации
        - Отсутствие реальных данных владельца
        - Русские индикаторы: «Данные скрыты», «Защита персональных данных»
        """
        privacy_indicators = [
            # English
            "whoisguard",
            "privacy protect",
            "private registration",
            "domain privacy",
            "redacted for privacy",
            "data protected",
            "not disclosed",
            "contact privacy",
            "withheld for privacy",
            # Russian
            "данные скрыты",
            "защита персональных данных",
            "частное лицо",
            "информация скрыта",
            "приватная регистрация",
            "защита конфиденциальности",
            "redacted",
            "privacy",
        ]

        # Проверяем имя и организацию
        name = (whois_data.get("registrant_name") or "").lower()
        org = (whois_data.get("registrant_org") or "").lower()

        return any(indicator in name or indicator in org for indicator in privacy_indicators)

    def _format_result(
        self, domain: str, whois_data: dict, is_private: bool
    ) -> dict[str, Any]:
        """Форматировать результат WHOIS."""
        return {
            "domain": domain,
            "registrar": whois_data.get("registrar"),
            "creation_date": whois_data.get("creation_date"),
            "expiration_date": whois_data.get("expiration_date"),
            "last_updated": whois_data.get("last_updated"),
            "name_servers": whois_data.get("name_servers", []),
            "registrant_name": None if is_private else whois_data.get("registrant_name"),
            "registrant_org": None if is_private else whois_data.get("registrant_org"),
            "registrant_country": whois_data.get("registrant_country"),
            "registrant_state": whois_data.get("registrant_state"),
            "registrant_city": whois_data.get("registrant_city"),
            "emails": [] if is_private else whois_data.get("emails", []),
            "dnssec": whois_data.get("dnssec"),
            "status": whois_data.get("status"),
            "is_private_registration": is_private,
        }

    async def health_check(self) -> bool:
        """Проверить доступность WHOIS."""
        try:
            import asyncio
            await asyncio.to_thread(python_whois.whois, "google.com")
            return True
        except Exception:
            return False


class MockWhoisConnector(BaseConnector):
    """Mock WHOIS connector for testing."""

    MOCK_DATA: dict[str, dict[str, Any]] = {
        "test-company.ru": {
            "domain": "test-company.ru",
            "registrar": "RU-CENTER-RU",
            "creation_date": "2020-01-15T00:00:00",
            "expiration_date": "2026-01-15T00:00:00",
            "last_updated": "2024-03-10T00:00:00",
            "name_servers": ["ns1.reg.ru", "ns2.reg.ru"],
            "registrant_name": None,
            "registrant_org": 'ООО "ТЕСТОВАЯ КОМПАНИЯ"',
            "registrant_country": "RU",
            "registrant_state": "Moscow",
            "registrant_city": "Moscow",
            "emails": ["admin@test-company.ru"],
            "dnssec": False,
            "status": ["clientTransferProhibited"],
            "is_private_registration": False,
        },
        "private-domain.ru": {
            "domain": "private-domain.ru",
            "registrar": "REG-RU",
            "creation_date": "2023-06-01T00:00:00",
            "expiration_date": "2025-06-01T00:00:00",
            "last_updated": "2024-01-01T00:00:00",
            "name_servers": ["ns1.reg.ru"],
            "registrant_name": None,
            "registrant_org": None,
            "registrant_country": None,
            "registrant_state": None,
            "registrant_city": None,
            "emails": [],
            "dnssec": False,
            "status": ["clientTransferProhibited"],
            "is_private_registration": True,
        },
    }

    @property
    def name(self) -> str:
        return "whois"

    @property
    def rate_limit(self) -> int:
        return 1000

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        domain = query.params.get("domain")
        if not domain:
            return ConnectorResult(
                success=False, source=self.name, error="Domain is required"
            )

        import asyncio
        await asyncio.sleep(0.05)

        data = self.MOCK_DATA.get(domain)
        if data:
            return ConnectorResult(
                success=True, data=data, source=f"{self.name}:mock"
            )

        # Default response for unknown domains
        return ConnectorResult(
            success=True,
            data={
                "domain": domain,
                "registrar": "Unknown Registrar",
                "creation_date": "2022-01-01T00:00:00",
                "expiration_date": "2027-01-01T00:00:00",
                "last_updated": None,
                "name_servers": [],
                "registrant_name": None,
                "registrant_org": None,
                "registrant_country": None,
                "registrant_state": None,
                "registrant_city": None,
                "emails": [],
                "dnssec": False,
                "status": [],
                "is_private_registration": False,
            },
            source=f"{self.name}:mock",
        )

    async def health_check(self) -> bool:
        return True

        for indicator in privacy_indicators:
            if indicator in name or indicator in org:
                return True

        # Если данных вообще нет — тоже считаем приватной регистрацией
        if not name and not org:
            return True

        return False

    def _format_result(
        self,
        domain: str,
        whois_data: dict,
        is_private: bool,
    ) -> dict[str, Any]:
        """Форматировать результат WHOIS запроса.

        ВАЖНО (152-ФЗ):
        - Если регистрация приватная — НЕ включаем персональные данные
        - Вместо этого указываем, что данные скрыты
        """
        result = {
            "domain": domain,
            "is_private_registration": is_private,
            "registrar": whois_data.get("registrar"),
            "creation_date": whois_data.get("creation_date"),
            "expiration_date": whois_data.get("expiration_date"),
            "last_updated": whois_data.get("last_updated"),
            "name_servers": whois_data.get("name_servers", []),
            "dnssec": whois_data.get("dnssec"),
            "status": whois_data.get("status"),
        }

        # Включаем персональные данные ТОЛЬКО если регистрация не приватная
        if not is_private:
            result["registrant"] = {
                "name": whois_data.get("registrant_name"),
                "org": whois_data.get("registrant_org"),
                "country": whois_data.get("registrant_country"),
                "state": whois_data.get("registrant_state"),
                "city": whois_data.get("registrant_city"),
                "emails": whois_data.get("emails", []),
            }
        else:
            result["registrant"] = None
            result["registrant_note"] = "Данные скрыты приватной регистрацией"

        return result

    async def health_check(self) -> bool:
        """Проверка доступности WHOIS сервисов."""
        try:
            # Пробуем запрос к известному домену
            result = await self.fetch(
                ConnectorQuery(
                    query_type="whois",
                    params={"domain": "google.com"},
                )
            )
            return result.success
        except Exception:
            return False


class WhoisAnalyzer:
    """Анализ WHOIS данных для выявления Red Flags."""

    def analyze(self, whois_data: dict) -> list[dict[str, Any]]:
        """Проанализировать WHOIS данные и вернуть Red Flags."""
        red_flags = []

        # Проверка даты регистрации
        creation_date = whois_data.get("creation_date")
        if creation_date:
            try:
                created = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
                age_days = (datetime.utcnow() - created.replace(tzinfo=None)).days

                if age_days < 365:
                    red_flags.append({
                        "id": "DOMAIN_RECENTLY_REGISTERED",
                        "priority": "MEDIUM",
                        "description": f"Домен зарегистрирован менее 1 года назад ({age_days} дней)",
                        "evidence": {"creation_date": creation_date, "age_days": age_days},
                    })
            except (ValueError, TypeError):
                pass

        # Проверка даты окончания
        expiration_date = whois_data.get("expiration_date")
        if expiration_date:
            try:
                expires = datetime.fromisoformat(expiration_date.replace("Z", "+00:00"))
                days_left = (expires.replace(tzinfo=None) - datetime.utcnow()).days

                if days_left < 30:
                    red_flags.append({
                        "id": "DOMAIN_EXPIRING_SOON",
                        "priority": "MEDIUM",
                        "description": f"Срок действия домена истекает через {days_left} дней",
                        "evidence": {"expiration_date": expiration_date, "days_left": days_left},
                    })
            except (ValueError, TypeError):
                pass

        # Проверка приватной регистрации
        if whois_data.get("is_private_registration"):
            red_flags.append({
                "id": "DOMAIN_PRIVATE_REGISTRATION",
                "priority": "LOW",
                "description": "Используется приватная регистрация домена",
                "evidence": {"domain": whois_data.get("domain")},
            })

        # Проверка DNSSEC
        if not whois_data.get("dnssec"):
            red_flags.append({
                "id": "DOMAIN_NO_DNSSEC",
                "priority": "LOW",
                "description": "Домен не использует DNSSEC",
                "evidence": {"domain": whois_data.get("domain")},
            })

        return red_flags
