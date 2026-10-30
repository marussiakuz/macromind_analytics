"""Tests for Checko Pydantic models."""

import pytest

from person_osint.checko_models import (
    CheckoBankResponse,
    CheckoBankruptcyResponse,
    CheckoCompanyResponse,
    CheckoContractsResponse,
    CheckoEnforcementsResponse,
    CheckoEntrepreneurResponse,
    CheckoFedresursResponse,
    CheckoFinancesResponse,
    CheckoFullCheckResult,
    CheckoInspectionsResponse,
    CheckoLegalCasesResponse,
    CheckoPersonResponse,
    CheckoReliabilityResponse,
    CheckoSearchResponse,
    CheckoTimelineResponse,
)


class TestCheckoCompanyResponse:
    def test_parse_minimal(self):
        data = {
            "data": {"ОГРН": "1224000000278", "ИНН": "4027148080", "НаимСокр": "ООО ДАТА МАКСИМУМ"},
            "meta": {"status": "ok", "today_request_count": 1, "balance": 100.0},
        }
        resp = CheckoCompanyResponse.model_validate(data)
        assert resp.meta.status == "ok"
        assert resp.data.ОГРН == "1224000000278"
        assert resp.data.ИНН == "4027148080"

    def test_parse_full(self):
        data = {
            "data": {
                "ОГРН": "1224000000278",
                "ИНН": "4027148080",
                "КПП": "402701001",
                "НаимСокр": "ООО ДАТА МАКСИМУМ",
                "НаимПолн": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ДАТА МАКСИМУМ",
                "Статус": {"Код": "ACTIVE", "Наим": "Действующая"},
                "Регион": {"Код": "40", "Наим": "Калужская область"},
                "ЮрАдрес": {"НасПункт": "Калуга", "АдресРФ": "248023, Калужская обл, г Калуга"},
                "ОКВЭД": {"Код": "63.11", "Наим": "Обработка данных"},
                "Руковод": [{"ФИО": "Иванов И.И.", "ИНН": "123456789012"}],
                "Учред": {"ФЛ": [{"ФИО": "Иванов И.И.", "ИНН": "123456789012", "Доля": {"Процент": 100}}]},
                "Контакты": {"Тел": ["+74842000000"], "Емэйл": ["info@example.com"]},
                "Налоги": {"ОсобРежим": ["УСН"]},
                "РМСП": {"Кат": "МАЛОЕ ПРЕДПРИЯТИЕ"},
                "Санкции": False,
                "НедобПост": False,
                "ДисквЛица": False,
                "МассРуковод": False,
                "МассУчред": False,
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoCompanyResponse.model_validate(data)
        assert resp.data.Статус.Код == "ACTIVE"
        assert len(resp.data.Руковод) == 1
        assert resp.data.Учред.ФЛ[0].Доля.Процент == 100
        assert resp.data.Контакты.Тел == ["+74842000000"]
        assert resp.data.Санкции is False

    def test_parse_empty_data(self):
        data = {"meta": {"status": "error", "message": "Not found"}}
        resp = CheckoCompanyResponse.model_validate(data)
        assert resp.meta.status == "error"
        assert resp.data is None


class TestCheckoEntrepreneurResponse:
    def test_parse(self):
        data = {
            "data": {
                "ОГРНИП": "310402910200035",
                "ИНН": "402907671076",
                "ФИО": "Иванов Иван Иванович",
                "Статус": {"Код": "ACTIVE", "Наим": "Действующий"},
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoEntrepreneurResponse.model_validate(data)
        assert resp.data.ОГРНИП == "310402910200035"


class TestCheckoPersonResponse:
    def test_parse(self):
        data = {
            "data": {
                "ИНН": "402907671076",
                "ФИО": "Иванов Иван Иванович",
                "Руковод": [{"ОГРН": "1224000000278", "НаимСокр": "ООО ДАТА МАКСИМУМ"}],
                "Санкции": False,
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoPersonResponse.model_validate(data)
        assert resp.data.ИНН == "402907671076"
        assert len(resp.data.Руковод) == 1


class TestCheckoFinancesResponse:
    def test_parse(self):
        data = {
            "company": {"ОГРН": "1027700198767", "ИНН": "7707049388"},
            "data": {"2023": {"1100": 1000000, "1200": 500000, "2110": 3000000}},
            "meta": {"status": "ok"},
        }
        resp = CheckoFinancesResponse.model_validate(data)
        assert resp.company.ИНН == "7707049388"
        assert resp.data["2023"]["2110"] == 3000000


class TestCheckoReliabilityResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7707049388"},
            "data": {
                "Масштаб": 85,
                "Номинальность": {"Уровень": 1, "Наим": "Риск не выявлен"},
                "ФинРиски": {"Уровень": 2, "Наим": "Низкие риски"},
                "Баланс": {"Полож": 60, "ТрВним": 30, "Негатив": 10},
                "Факторы": [{"Код": "AGE", "Тип": "Полож", "Вес": 5.0, "Текст": "Более 3 лет"}],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoReliabilityResponse.model_validate(data)
        assert resp.data.Масштаб == 85
        assert resp.data.Баланс.Полож == 60
        assert len(resp.data.Факторы) == 1


class TestCheckoSearchResponse:
    def test_parse_org(self):
        data = {
            "data": {
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{"ОГРН": "1224000000278", "ИНН": "4027148080", "НаимСокр": "ООО ДАТА МАКСИМУМ"}],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoSearchResponse.model_validate(data)
        assert resp.data.СтрВсего == 1
        assert len(resp.data.Записи) == 1


class TestCheckoTimelineResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7724408012"},
            "data": [
                {"Дата": "2020-01-01", "Событие": "Регистрация"},
                {"Дата": "2021-06-15", "Событие": "Смена директора"},
            ],
            "meta": {"status": "ok"},
        }
        resp = CheckoTimelineResponse.model_validate(data)
        assert len(resp.data) == 2
        assert resp.data[0].Событие == "Регистрация"


class TestCheckoLegalCasesResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7804500856"},
            "data": {
                "ЗапВсего": 5,
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "ОбщСуммИск": 1500000.0,
                "Записи": [{
                    "Номер": "А40-123456/2023",
                    "Дата": "2023-04-03",
                    "Тип": "Г",
                    "Суд": "Арбитражный суд г. Москвы",
                    "Ист": [{"ИНН": "7707049388", "Наим": "ПАО Сбербанк"}],
                    "Ответ": [{"ИНН": "7804500856", "Наим": "ООО Рога и Копыта"}],
                    "СуммИск": 500000.0,
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoLegalCasesResponse.model_validate(data)
        assert resp.data.ЗапВсего == 5
        assert resp.data.Записи[0].Тип == "Г"


class TestCheckoEnforcementsResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7707049388"},
            "data": {
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{
                    "ИспПрНомер": "12345/2023",
                    "ИспПрДата": "2023-05-01",
                    "ПредмИсп": "Взыскание долга",
                    "СумДолг": 100000.0,
                    "ОстЗадолж": 50000.0,
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoEnforcementsResponse.model_validate(data)
        assert resp.data.Записи[0].СумДолг == 100000.0


class TestCheckoContractsResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7707049388"},
            "data": {
                "ЗапВсего": 10,
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{
                    "РегНомер": "1234567890",
                    "Дата": "2023-01-15",
                    "Цена": 500000,
                    "Заказ": {"ИНН": "7707049388", "НаимСокр": "ПАО Сбербанк"},
                    "Постав": [{"ИНН": "123456789012", "НаимСокр": "ИП Иванов"}],
                    "Объекты": [{"Наим": "Поставка оборудования"}],
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoContractsResponse.model_validate(data)
        assert resp.data.Записи[0].Цена == 500000


class TestCheckoFedresursResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7207018737"},
            "data": {
                "ЗапВсего": 2,
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{
                    "GUID": "abc-123",
                    "Дата": "2024-01-01",
                    "Тип": "CreditorIntentionGoToCourt",
                    "ТипНаим": "Намерение кредитора обратиться в суд",
                    "Публикатор": "7207018737",
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoFedresursResponse.model_validate(data)
        assert resp.data.Записи[0].Тип == "CreditorIntentionGoToCourt"


class TestCheckoBankruptcyResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7724408012"},
            "data": {
                "ЗапВсего": 1,
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{
                    "GUID": "def-456",
                    "Дата": "2024-03-01",
                    "Тип": "BankruptDecision",
                    "ТипНаим": "Решение о признании банкротом",
                    "НомерДела": "А40-123456/2024",
                    "Суд": "Арбитражный суд г. Москвы",
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoBankruptcyResponse.model_validate(data)
        assert resp.data.Записи[0].НомерДела == "А40-123456/2024"


class TestCheckoInspectionsResponse:
    def test_parse(self):
        data = {
            "company": {"ИНН": "7707049388"},
            "data": {
                "ЗапВсего": 3,
                "СтрВсего": 1,
                "СтрТекущ": 1,
                "Записи": [{
                    "Номер": "12345",
                    "Статус": "Завершена",
                    "Заверш": True,
                    "Наруш": True,
                    "ДатаНач": "2023-06-01",
                    "ДатаОконч": "2023-06-15",
                    "Цель": "Плановая проверка",
                    "ОргКонтр": {"Наим": "Роспотребнадзор"},
                }],
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoInspectionsResponse.model_validate(data)
        assert resp.data.Записи[0].Заверш is True
        assert resp.data.Записи[0].Наруш is True


class TestCheckoBankResponse:
    def test_parse(self):
        data = {
            "data": {
                "БИК": "042908612",
                "Наим": "ПАО Сбербанк",
                "Адрес": "г. Москва",
                "Тип": "Коммерческий банк",
                "КорСчет": {"Номер": "30101810400000000225"},
            },
            "meta": {"status": "ok"},
        }
        resp = CheckoBankResponse.model_validate(data)
        assert resp.data.БИК == "042908612"
        assert resp.data.КорСчет.Номер == "30101810400000000225"


class TestCheckoFullCheckResult:
    def test_parse(self):
        result = CheckoFullCheckResult()
        assert result.company is None
        assert result.errors == []

    def test_with_data(self):
        company_data = {
            "data": {"ОГРН": "1224000000278", "ИНН": "4027148080"},
            "meta": {"status": "ok"},
        }
        result = CheckoFullCheckResult(
            company=CheckoCompanyResponse.model_validate(company_data),
            errors=[],
        )
        assert result.company.data.ИНН == "4027148080"