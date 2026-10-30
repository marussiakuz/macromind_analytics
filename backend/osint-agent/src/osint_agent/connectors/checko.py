"""Checko API v2: company records, entrepreneurs, persons, search and optional reliability."""

from typing import Any

import httpx

from osint_agent.config import settings
from osint_agent.connectors.base import BaseConnector
from osint_agent.connectors.egrul import validate_inn
from osint_agent.models import ConnectorQuery, ConnectorResult

SEARCH_BY = {
    "name",
    "founder-name",
    "leader-name",
    "okved",
    "reg-date",
    "upd-date",
    "phone",
    "email",
}


class CheckoConnector(BaseConnector):
    BASE_URL = "https://api.checko.ru/v2"
    name = "checko"
    rate_limit = 30

    async def fetch(self, query: ConnectorQuery) -> ConnectorResult:
        key = settings.checko_api_key.get_secret_value()
        if not key:
            return self._error("CHECKO_API_KEY не настроен")
        query_type = query.query_type
        params = query.params or {}

        if query_type == "company_search":
            return await self._search(key, params)

        inn = params.get("inn", "")
        if not isinstance(inn, str) or not inn.isascii() or not validate_inn(inn):
            return self._error("Некорректный ИНН")
        inn = inn.replace(" ", "").replace("-", "")
        if query_type == "counterparty_reliability":
            method = "reliability"
        elif query_type == "person_legal":
            if len(inn) != 12:
                return self._error("ИНН физлица должен содержать 12 цифр")
            method = "person"
        elif query_type == "company_finances":
            if len(inn) != 10:
                return self._error("Финансовая отчетность доступна только для организаций (ИНН 10 цифр)")
            method = "finances"
        elif query_type == "company_timeline":
            method = "timeline"
        elif query_type == "company_registry":
            method = params.get("method")
            allowed = {
                "legal-cases",
                "enforcements",
                "contracts",
                "fedresurs",
                "bankruptcy-messages",
                "inspections",
            }
            if method not in allowed:
                return self._error("Некорректный метод реестра")
        else:
            method = "company" if len(inn) == 10 else "entrepreneur"
        try:
            client = await self.get_client()
            # Keep the API key out of URLs, audit query params and redirects.
            request_body: dict[str, Any] = {"key": key, "inn": inn}
            if query_type == "company_registry":
                # extra filters for list methods (contracts requires law)
                for field in ("law", "role", "sort", "limit", "page", "type", "actual", "active", "date_from", "date_to"):
                    value = params.get(field)
                    if value is not None and value != "":
                        request_body[field] = value
            response = await client.post(
                f"{self.BASE_URL}/{method}",
                json=request_body,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
                return self._error("Некорректный ответ Checko")
            if payload["meta"].get("status") != "ok":
                message = str(payload["meta"].get("message") or "Запрос отклонён")
                return self._error("Checko: " + message.replace(key, "[скрыто]")[:300])
            data = payload.get("data")
            if query_type == "company_finances":
                # finances.md: data is a year→lines map and may be empty
                company_meta = payload.get("company") or {}
                if not isinstance(payload.get("data"), dict):
                    return self._error("Некорректные данные Checko")
                if company_meta.get("ИНН") and company_meta.get("ИНН") != inn:
                    return self._error("Checko вернул данные другого ИНН")
                return ConnectorResult(
                    success=True,
                    source=self.name,
                    data=self._normalize_finances(inn, payload),
                )
            if query_type == "company_timeline":
                # timeline.md: data is a list of events; empty list is valid
                if not isinstance(payload.get("data"), list):
                    return self._error("Некорректные данные Checko")
                identity = payload.get("company") or payload.get("entrepreneur") or payload.get("person") or {}
                if identity.get("ИНН") and identity.get("ИНН") != inn:
                    return self._error("Checko вернул данные другого ИНН")
                return ConnectorResult(
                    success=True,
                    source=self.name,
                    data=self._normalize_timeline(inn, payload),
                )
            if query_type == "company_registry":
                raw = payload.get("data")
                if not isinstance(raw, dict):
                    return self._error("Некорректные данные Checko")
                identity = payload.get("company") or payload.get("entrepreneur") or payload.get("person") or {}
                if identity.get("ИНН") and identity.get("ИНН") != inn:
                    return self._error("Checko вернул данные другого ИНН")
                normalized = self._normalize_registry(inn, payload, method)
                if not normalized:
                    return self._error("Некорректные данные Checko")
                return ConnectorResult(success=True, source=self.name, data=normalized)
            if not data:
                return self._error("Контрагент не найден")
            if not isinstance(data, dict):
                return self._error("Некорректные данные Checko")
            if query_type == "counterparty_reliability":
                normalized = {"inn": inn, "assessment": data, "source": "checko"}
            elif query_type == "person_legal":
                if data.get("ИНН") != inn:
                    return self._error("Checko вернул данные другого ИНН")
                normalized = self._normalize_person(data)
            else:
                if data.get("ИНН") != inn:
                    return self._error("Checko вернул данные другого ИНН")
                normalized = self._normalize(data, len(inn) == 12)
            return ConnectorResult(success=True, source=self.name, data=normalized)
        except httpx.HTTPStatusError as exc:
            return self._http_error(exc)
        except httpx.TimeoutException:
            return self._error("Checko не ответил вовремя")
        except httpx.RequestError:
            return self._error("Не удалось подключиться к Checko")
        except (ValueError, TypeError, AttributeError):
            return self._error("Некорректный ответ Checko")

    def _http_error(self, exc: httpx.HTTPStatusError) -> ConnectorResult:
        status = exc.response.status_code
        message = ""
        try:
            payload = exc.response.json()
            message = ((payload.get("meta") or {}).get("message") or "").strip()
        except Exception:
            message = ""
        if message:
            return self._error(message[:300])
        if status == 403:
            return self._error("Превышен лимит запросов или метод недоступен по тарифу")
        return self._error(f"Сервис данных не ответил (HTTP {status})")

    async def _search(self, key: str, params: dict[str, Any]) -> ConnectorResult:
        """Поиск организаций/ИП (search.md)."""
        by = str(params.get("by") or "name")
        obj = str(params.get("obj") or "org")
        search_query = str(params.get("query") or "").strip()
        if by not in SEARCH_BY:
            return self._error("Некорректный тип поиска")
        if obj not in ("org", "ent"):
            return self._error("Некорректный тип объекта поиска")
        if not search_query:
            return self._error("Пустой поисковый запрос")
        # Only name-like searches require 4+ characters (search.md).
        if by in ("name", "founder-name", "leader-name") and len(search_query) < 4:
            return self._error("Для поиска по наименованию/ФИО нужно минимум 4 символа")

        body: dict[str, Any] = {"key": key, "by": by, "obj": obj, "query": search_query}
        for field in ("region", "okved", "opf", "codes", "limit", "page"):
            value = params.get(field)
            if value is not None and value != "":
                body[field] = value
        if params.get("active") is not None:
            body["active"] = "true" if params.get("active") else "false"

        try:
            client = await self.get_client()
            response = await client.post(
                f"{self.BASE_URL}/search",
                json=body,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
                return self._error("Некорректный ответ Checko")
            if payload["meta"].get("status") != "ok":
                message = str(payload["meta"].get("message") or "Запрос отклонён")
                return self._error("Checko: " + message.replace(key, "[скрыто]")[:300])
            data = payload.get("data") or {}
            if not isinstance(data, dict):
                return self._error("Некорректные данные Checko")
            items = data.get("Записи") or []
            results = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if obj == "ent":
                    results.append(
                        {
                            "inn": item.get("ИНН"),
                            "ogrn": item.get("ОГРНИП"),
                            "name": item.get("ФИО"),
                            "full_name": item.get("ФИО"),
                            "entity_type": "entrepreneur",
                            "registration_date": item.get("ДатаРег"),
                            "status": item.get("Статус"),
                            "liquidation_date": item.get("ДатаПрекращ"),
                            "okved": item.get("ОКВЭД"),
                            "address": None,
                        }
                    )
                else:
                    results.append(
                        {
                            "inn": item.get("ИНН"),
                            "ogrn": item.get("ОГРН"),
                            "name": item.get("НаимСокр") or item.get("НаимПолн"),
                            "full_name": item.get("НаимПолн"),
                            "entity_type": "company",
                            "registration_date": item.get("ДатаРег"),
                            "status": item.get("Статус"),
                            "liquidation_date": item.get("ДатаЛикв"),
                            "okved": item.get("ОКВЭД"),
                            "address": item.get("ЮрАдрес"),
                        }
                    )
            meta = payload.get("meta") or {}
            return ConnectorResult(
                success=True,
                source=self.name,
                data={
                    "by": by,
                    "obj": obj,
                    "query": search_query,
                    "total_pages": data.get("СтрВсего"),
                    "page": data.get("СтрТекущ"),
                    "results": results,
                    "source": "checko",
                    "balance": meta.get("balance"),
                    "today_request_count": meta.get("today_request_count"),
                },
            )
        except httpx.HTTPStatusError as exc:
            return self._http_error(exc)
        except httpx.TimeoutException:
            return self._error("Checko не ответил вовремя")
        except httpx.RequestError:
            return self._error("Не удалось подключиться к Checko")
        except (ValueError, TypeError, AttributeError):
            return self._error("Некорректный ответ Checko")

    def _error(self, message: str) -> ConnectorResult:
        return ConnectorResult(success=False, source=self.name, error=message)

    @staticmethod
    def _normalize_company_link(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "ogrn": item.get("ОГРН"),
            "inn": item.get("ИНН"),
            "name": item.get("НаимСокр") or item.get("НаимПолн"),
            "full_name": item.get("НаимПолн"),
            "registration_date": item.get("ДатаРег"),
            "status": item.get("Статус"),
            "liquidation_date": item.get("ДатаЛикв"),
            "address": item.get("ЮрАдрес"),
            "okved": item.get("ОКВЭД"),
        }

    @classmethod
    def _normalize_finances(cls, inn: str, payload: dict[str, Any]) -> dict[str, Any]:
        """finances.md → годы, выручка (2110), чистая прибыль (2400), ссылки БФО."""
        company_meta = payload.get("company") or {}
        raw = payload.get("data") or {}
        # extended=true → {СумОтч, СумПрдщ, СумПрдшв}; standard → int
        def line_value(cell: Any) -> float | None:
            if isinstance(cell, (int, float)):
                return float(cell)
            if isinstance(cell, dict):
                current = cell.get("СумОтч")
                if isinstance(current, (int, float)):
                    return float(current)
            return None

        years: list[dict[str, Any]] = []
        for year_key, lines in raw.items():
            if not isinstance(lines, dict):
                continue
            try:
                year = int(year_key)
            except (TypeError, ValueError):
                continue
            years.append(
                {
                    "year": year,
                    "revenue": line_value(lines.get("2110") if "2110" in lines else lines.get(2110)),
                    "net_profit": line_value(lines.get("2400") if "2400" in lines else lines.get(2400)),
                }
            )
        years.sort(key=lambda item: item["year"])

        reports_raw = (payload.get("bo.nalog.ru") or {}).get("Отчет") or {}
        report_links = {}
        for year_key, url in reports_raw.items():
            if url:
                report_links[str(year_key)] = url

        return {
            "inn": inn,
            "ogrn": company_meta.get("ОГРН"),
            "name": company_meta.get("НаимСокр") or company_meta.get("НаимПолн"),
            "full_name": company_meta.get("НаимПолн"),
            "entity_type": "company",
            "years": years,
            "report_links": report_links,
            "source": "checko",
        }

    @classmethod
    def _normalize_registry(cls, inn: str, payload: dict[str, Any], method: str) -> dict[str, Any]:
        """Списочные реестры: legal-cases / enforcements / contracts / fedresurs / bankruptcy / inspections."""
        company_meta = payload.get("company") or {}
        entrepreneur_meta = payload.get("entrepreneur") or {}
        person_meta = payload.get("person") or {}
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return {}
        raw_items = data.get("Записи") or []
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            items.append(cls._registry_row(method, item))
        name = (
            person_meta.get("ФИО")
            or entrepreneur_meta.get("ФИО")
            or company_meta.get("НаимСокр")
            or company_meta.get("НаимПолн")
        )
        return {
            "inn": inn,
            "name": name,
            "full_name": company_meta.get("НаимПолн") or entrepreneur_meta.get("ФИО") or person_meta.get("ФИО"),
            "ogrn": company_meta.get("ОГРН") or entrepreneur_meta.get("ОГРНИП"),
            "method": method,
            "total": data.get("ЗапВсего") if data.get("ЗапВсего") is not None else len(items),
            "total_pages": data.get("СтрВсего"),
            "items": items,
            "source": "checko",
        }

    @staticmethod
    def _registry_row(method: str, item: dict[str, Any]) -> dict[str, Any]:
        """Приведение строки реестра к плоскому виду для UI."""
        if method == "legal-cases":
            plaintiffs = ", ".join(
                p.get("Наим") or p.get("ИНН") or "" for p in item.get("Ист") or [] if isinstance(p, dict)
            )
            defendants = ", ".join(
                p.get("Наим") or p.get("ИНН") or "" for p in item.get("Ответ") or [] if isinstance(p, dict)
            )
            return {
                "id": item.get("UUID") or item.get("Номер"),
                "title": f"Дело №{item.get('Номер') or '—'}",
                "date": item.get("Дата"),
                "status": item.get("ИсходТекст") or ("В производстве" if item.get("ПрАктив") else None),
                "amount": item.get("СуммИск"),
                "url": item.get("СтрКАД"),
                "fields": {
                    "Тип": item.get("Тип"),
                    "Суд": item.get("Суд"),
                    "Истцы": plaintiffs,
                    "Ответчики": defendants,
                    "Следующее заседание": item.get("ДатаСлед"),
                    "Победитель": item.get("Победитель"),
                    "Уверенность": item.get("ИсходДост"),
                },
            }
        if method == "enforcements":
            return {
                "id": item.get("ИспПрНомер"),
                "title": f"ИП №{item.get('ИспПрНомер') or '—'}",
                "date": item.get("ИспПрДата"),
                "status": item.get("ПредмИсп"),
                "amount": item.get("ОстЗадолж") if item.get("ОстЗадолж") is not None else item.get("СумДолг"),
                "url": None,
                "fields": {
                    "Должник": item.get("ДолжНаим"),
                    "Предмет исполнения": item.get("ПредмИсп"),
                    "Сумма долга": item.get("СумДолг"),
                    "Остаток": item.get("ОстЗадолж"),
                    "Документ": item.get("ИспДокНомер"),
                    "Приставы": item.get("СудПристНаим"),
                },
            }
        if method == "contracts":
            customer = item.get("Заказ") or {}
            suppliers = ", ".join(
                s.get("НаимСокр") or s.get("ФИО") or s.get("ИНН") or ""
                for s in item.get("Постав") or []
                if isinstance(s, dict)
            )
            objects = ", ".join(
                o.get("Наим") or "" for o in item.get("Объекты") or [] if isinstance(o, dict)
            )
            return {
                "id": item.get("РегНомер"),
                "title": f"Контракт №{item.get('РегНомер') or '—'}",
                "date": item.get("Дата"),
                "status": item.get("ДатаИсп") and f"исполнение до {item.get('ДатаИсп')}",
                "amount": item.get("Цена"),
                "url": item.get("СтрЕИС"),
                "fields": {
                    "Заказчик": customer.get("НаимСокр") or customer.get("ИНН"),
                    "Поставщики": suppliers,
                    "Объекты": objects,
                    "Регион": item.get("РегионКод"),
                },
            }
        if method == "fedresurs":
            return {
                "id": item.get("GUID"),
                "title": item.get("ТипНаим") or item.get("Тип") or "Сообщение",
                "date": item.get("Дата"),
                "status": item.get("Тип"),
                "amount": None,
                "url": item.get("URL"),
                "fields": {
                    "Тип": item.get("Тип"),
                    "Публикатор": item.get("Публикатор"),
                    "Участники": ", ".join(item.get("Участники") or []),
                },
            }
        if method == "bankruptcy-messages":
            return {
                "id": item.get("GUID"),
                "title": item.get("ТипНаим") or item.get("Тип") or "Запись ЕФРСБ",
                "date": item.get("Дата"),
                "status": item.get("РешенСуда"),
                "amount": None,
                "url": item.get("URL"),
                "fields": {
                    "Тип": item.get("Тип"),
                    "Дело": item.get("НомерДела"),
                    "Суд": item.get("Суд"),
                    "Решение": item.get("РешенСуда"),
                },
            }
        # inspections
        org = item.get("ОргКонтр") or {}
        return {
            "id": item.get("Номер"),
            "title": f"Проверка №{item.get('Номер') or '—'}",
            "date": item.get("ДатаНач"),
            "status": item.get("Статус"),
            "amount": None,
            "url": None,
            "fields": {
                "Тип": item.get("ТипПров"),
                "Цель": item.get("Цель"),
                "Окончание": item.get("ДатаОконч"),
                "Орган": org.get("Наим"),
                "Класс риска": item.get("КлассРиск"),
                "Нарушения": "да" if item.get("Наруш") else ("нет" if item.get("Наруш") is False else None),
                "Завершена": "да" if item.get("Заверш") else ("нет" if item.get("Заверш") is False else None),
            },
        }

    @classmethod
    def _normalize_timeline(cls, inn: str, payload: dict[str, Any]) -> dict[str, Any]:
        """timeline.md → список событий с датами (company / entrepreneur / person)."""
        company_meta = payload.get("company") or {}
        entrepreneur_meta = payload.get("entrepreneur") or {}
        person_meta = payload.get("person") or {}
        events = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            date = item.get("Дата")
            event = item.get("Событие")
            if date or event:
                events.append({"date": date, "event": event})
        name = (
            person_meta.get("ФИО")
            or entrepreneur_meta.get("ФИО")
            or company_meta.get("НаимСокр")
            or company_meta.get("НаимПолн")
        )
        entity_type = "company" if company_meta else ("entrepreneur" if entrepreneur_meta else ("person" if person_meta else "unknown"))
        return {
            "inn": inn,
            "ogrn": company_meta.get("ОГРН") or entrepreneur_meta.get("ОГРНИП"),
            "name": name,
            "full_name": company_meta.get("НаимПолн") or entrepreneur_meta.get("ФИО") or person_meta.get("ФИО"),
            "entity_type": entity_type,
            "events": events,
            "source": "checko",
        }

    @classmethod
    def _normalize_person(cls, data: dict[str, Any]) -> dict[str, Any]:
        managed = [cls._normalize_company_link(item) for item in data.get("Руковод") or []]
        founded = [cls._normalize_company_link(item) for item in data.get("Учред") or []]
        businesses = [
            {
                "ogrnip": item.get("ОГРНИП"),
                "inn": item.get("ИНН"),
                "name": item.get("ФИО"),
                "type": item.get("Тип"),
                "registration_date": item.get("ДатаРег"),
                "status": item.get("Статус"),
                "termination_date": item.get("ДатаПрекращ"),
                "okved": item.get("ОКВЭД"),
            }
            for item in data.get("ИП") or []
        ]
        return {
            "inn": data["ИНН"],
            "full_name": data.get("ФИО"),
            "entity_type": "person",
            "managed_companies": managed,
            "founded_companies": founded,
            "entrepreneurships": businesses,
            "trademarks": data.get("ТоварЗнак") or [],
            "bankruptcy_messages": data.get("ЕФРСБ") or [],
            "risk_factors": {
                "unfair_supplier": data.get("НедобПост"),
                "mass_director": data.get("МассРуковод"),
                "mass_founder": data.get("МассУчред"),
                "sanctioned": data.get("Санкции"),
                "sanctioned_countries": data.get("СанкцииСтраны") or [],
            },
            "source": "checko",
        }

    @staticmethod
    def _normalize(data: dict[str, Any], entrepreneur: bool) -> dict[str, Any]:
        def obj(key):
            return data.get(key) or {}

        shareholders = []
        founders = obj("Учред")
        for group, kind in (("ФЛ", "person"), ("РосОрг", "company"), ("ИнОрг", "company")):
            for founder in founders.get(group) or []:
                shareholders.append(
                    {
                        "name": founder.get("ФИО")
                        or founder.get("НаимСокр")
                        or founder.get("НаимПолн")
                        or "",
                        "type": kind,
                        "inn": founder.get("ИНН"),
                        "share_percent": (founder.get("Доля") or {}).get("Процент"),
                    }
                )
        directors = data.get("Руковод") or []
        risk_fields = {
            "unreliable_address": obj("ЮрАдрес").get("Недост"),
            "disqualified_management": data.get("ДисквЛица"),
            "mass_director": data.get("МассРуковод"),
            "mass_founder": data.get("МассУчред"),
            "unfair_supplier": data.get("НедобПост"),
            "illegal_financial_activity": data.get("НелегалФин"),
            "sanctioned": data.get("Санкции"),
            "sanctioned_founder": data.get("СанкцУчр"),
        }
        name = data.get("ФИО") if entrepreneur else data.get("НаимСокр") or data.get("НаимПолн")
        return {
            "inn": data["ИНН"],
            "ogrn": data.get("ОГРНИП" if entrepreneur else "ОГРН"),
            "name": name,
            "full_name": data.get("ФИО") if entrepreneur else data.get("НаимПолн"),
            "entity_type": "entrepreneur" if entrepreneur else "company",
            "legal_form": "ИП" if entrepreneur else obj("ОКОПФ").get("Наим"),
            "registration_date": data.get("ДатаРег"),
            "status": obj("Статус").get("Наим"),
            "status_code": obj("Статус").get("Код"),
            "address": obj("ЮрАдрес").get("АдресРФ"),
            "okved_main": obj("ОКВЭД").get("Код"),
            "okved_description": obj("ОКВЭД").get("Наим"),
            "charter_capital": obj("УстКап").get("Сумма"),
            "director": directors[0].get("ФИО") if directors else None,
            "directors": directors,
            "shareholders": shareholders,
            "risk_factors": risk_fields,
            "contacts": obj("Контакты"),
            "source": "checko",
        }

    async def health_check(self) -> bool:
        # No billable lookup merely to test health.
        return bool(settings.checko_api_key.get_secret_value())
