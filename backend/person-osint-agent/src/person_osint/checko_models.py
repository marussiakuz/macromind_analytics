"""Pydantic models for Checko API responses.

All 14 methods: company, entrepreneur, person, finances, reliability,
search, timeline, legal-cases, enforcements, contracts, fedresurs,
bankruptcy-messages, inspections, bank.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# === Shared / Meta ===


class CheckoMeta(BaseModel):
    status: str = ""
    today_request_count: int = 0
    balance: float = 0
    message: str = ""


class CheckoRegion(BaseModel):
    Код: str = ""
    Наим: str = ""


class CheckoStatus(BaseModel):
    ОгрДоступ: bool = False
    Код: str = ""
    Наим: str = ""
    ДатаЗаписи: str = ""


class CheckoOkved(BaseModel):
    Код: str = ""
    Наим: str = ""
    Версия: str = ""


class CheckoClassifier(BaseModel):
    Код: str = ""
    Наим: str = ""


class CheckoRegAuthority(BaseModel):
    КодОрг: str = ""
    НаимОрг: str = ""
    АдресОрг: str = ""
    Дата: str = ""


class CheckoRegPFR(BaseModel):
    ДатаРег: str = ""
    РегНомер: str = ""
    КодОрг: str = ""
    НаимОрг: str = ""


class CheckoRegFSS(BaseModel):
    ДатаРег: str = ""
    РегНомер: str = ""
    КодОрг: str = ""
    НаимОрг: str = ""


class CheckoCapital(BaseModel):
    Тип: str = ""
    Сумма: int = 0


class CheckoDolya(BaseModel):
    Номинал: float = 0
    Процент: float = 0


class CheckoZalogHolder(BaseModel):
    ИНН: str = ""
    ОГРН: str = ""
    НаимПолн: str = ""
    ФИО: str = ""


class CheckoNotarial(BaseModel):
    Дата: str = ""
    Номер: str = ""


class CheckoObremenenie(BaseModel):
    Тип: str = ""
    Залогодерж: CheckoZalogHolder | None = None
    Нотариал: CheckoNotarial | None = None


class CheckoLicense(BaseModel):
    Номер: str = ""
    Дата: str = ""
    ДатаНач: str = ""
    ДатаОконч: str = ""
    ЛицОрг: str = ""
    ВидДеят: list[str] = Field(default_factory=list)


class CheckoTrademark(BaseModel):
    ID: int = 0
    URL: str = ""
    ДатаРег: str = ""
    ДатаОконч: str = ""


class CheckoContactInfo(BaseModel):
    Тел: list[str] = Field(default_factory=list)
    Емэйл: list[str] = Field(default_factory=list)
    ВебСайт: str = ""


class CheckoNalogi(BaseModel):
    ОсобРежим: list[str] = Field(default_factory=list)
    СведУпл: list[dict[str, Any]] = Field(default_factory=list)
    СумУпл: float = 0
    СведУплГод: str = ""
    СумНедоим: float = 0
    НедоимДата: str = ""


class CheckoMSPE(BaseModel):
    Кат: str = ""
    ДатаВкл: str = ""


class CheckoMSPSupport(BaseModel):
    Дата: str = ""
    Тип: str = ""
    Форма: str = ""
    НаимОрг: str = ""
    ИНН: str = ""
    Размер: str = ""
    Наруш: bool = False


class CheckoBankruptcyMsg(BaseModel):
    Тип: str = ""
    Дата: str = ""
    Дело: str = ""


class CheckoDisqualifiedPerson(BaseModel):
    ОгрДоступ: bool = False
    ФИО: str = ""
    ИНН: str = ""
    ВидДолжн: str = ""
    НаимДолжн: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    МассРуковод: bool = False
    ДисквЛицо: bool = False
    ДисквДатаНач: str = ""
    ДисквДатаОконч: str = ""
    СвязРуковод: list[str] = Field(default_factory=list)
    СвязУчред: list[str] = Field(default_factory=list)
    ДатаЗаписи: str = ""


# Alias for Руковод items
CheckoRukovoditel = CheckoDisqualifiedPerson


class CheckoUchredFL(BaseModel):
    ОгрДоступ: bool = False
    ФИО: str = ""
    ИНН: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    МассУчред: bool = False
    Доля: CheckoDolya | None = None
    Обрем: list[CheckoObremenenie] = Field(default_factory=list)
    СвязРуковод: list[str] = Field(default_factory=list)
    СвязУчред: list[str] = Field(default_factory=list)
    ДатаЗаписи: str = ""


class CheckoUchredRO(BaseModel):
    ОгрДоступ: bool = False
    ОГРН: str = ""
    ИНН: str = ""
    ДатаОГРН: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    Доля: CheckoDolya | None = None
    Обрем: list[CheckoObremenenie] = Field(default_factory=list)
    СвязУчред: list[str] = Field(default_factory=list)
    ДатаЗаписи: str = ""


class CheckoUchredIO(BaseModel):
    ОгрДоступ: bool = False
    НаимПолн: str = ""
    Страна: str = ""
    Адрес: str = ""
    РегНомер: str = ""
    ДатаРег: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    Доля: CheckoDolya | None = None
    Обрем: list[CheckoObremenenie] = Field(default_factory=list)
    ДатаЗаписи: str = ""


class CheckoUprKom(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    ДатаОГРН: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""


class CheckoUchredPIF(BaseModel):
    ОгрДоступ: bool = False
    Наим: str = ""
    УпрКом: CheckoUprKom | None = None
    Недост: bool = False
    НедостОпис: str = ""
    Доля: CheckoDolya | None = None
    Обрем: list[CheckoObremenenie] = Field(default_factory=list)
    ДатаЗаписи: str = ""


class CheckoOrganExecutor(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    НаимПолн: str = ""


class CheckoPersonExecutor(BaseModel):
    ФИО: str = ""
    ИНН: str = ""


class CheckoUchredRF(BaseModel):
    ОгрДоступ: bool = False
    Тип: str = ""
    Регион: CheckoRegion | None = None
    ОргОсущПрав: list[CheckoOrganExecutor] = Field(default_factory=list)
    ФЛОсущПрав: list[CheckoPersonExecutor] = Field(default_factory=list)
    Недост: bool = False
    НедостОпис: str = ""
    Доля: CheckoDolya | None = None
    Обрем: list[CheckoObremenenie] = Field(default_factory=list)
    СвязУчред: list[str] = Field(default_factory=list)
    ДатаЗаписи: str = ""


class CheckoUchrediteli(BaseModel):
    ФЛ: list[CheckoUchredFL] = Field(default_factory=list)
    РосОрг: list[CheckoUchredRO] = Field(default_factory=list)
    ИнОрг: list[CheckoUchredIO] = Field(default_factory=list)
    ПИФ: list[CheckoUchredPIF] = Field(default_factory=list)
    РФ: list[CheckoUchredRF] = Field(default_factory=list)


class CheckoUprOrg(BaseModel):
    ОгрДоступ: bool = False
    ОГРН: str = ""
    ИНН: str = ""
    ДатаОГРН: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ИнСтрана: str = ""
    ИнАдрес: str = ""
    ИнРегНомер: str = ""
    ИнДатаРег: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    ДатаЗаписи: str = ""


class CheckoSvyazItem(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoSubdivision(BaseModel):
    ОгрДоступ: bool = False
    НаимПолн: str = ""
    КПП: str = ""
    Адрес: str = ""
    Страна: str = ""
    ИнАдрес: str = ""


class CheckoPodrazdel(BaseModel):
    Филиал: list[CheckoSubdivision] = Field(default_factory=list)
    Представ: list[CheckoSubdivision] = Field(default_factory=list)


class CheckoPravopredshestv(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    НаимПолн: str = ""


class CheckoDerzhReestr(BaseModel):
    ОгрДоступ: bool = False
    ОГРН: str = ""
    ИНН: str = ""
    НаимПолн: str = ""


class CheckoNedobPostZap(BaseModel):
    РеестрНомер: str = ""
    ДатаПуб: str = ""
    ДатаУтв: str = ""
    ЗаказНаимСокр: str = ""
    ЗаказНаимПолн: str = ""
    ЗаказИНН: str = ""
    ЗаказКПП: str = ""
    ЗакупНомер: str = ""
    ЗакупОпис: str = ""
    ЦенаКонтр: int = 0


class CheckoYurAddress(BaseModel):
    НасПункт: str = ""
    АдресРФ: str = ""
    ИдГАР: str = ""
    Недост: bool = False
    НедостОпис: str = ""
    МассАдрес: list[str] = Field(default_factory=list)


class CheckoLikvid(BaseModel):
    Дата: str = ""
    Наим: str = ""


# === 1. Company (ЕГРЮЛ) ===


class CheckoCompanyData(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    ОКПО: str = ""
    ДатаРег: str = ""
    ДатаОГРН: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    НаимАнгл: str = ""
    Статус: CheckoStatus | None = None
    Ликвид: CheckoLikvid | None = None
    Регион: CheckoRegion | None = None
    ЮрАдрес: CheckoYurAddress | None = None
    ОКВЭД: CheckoOkved | None = None
    ОКВЭДДоп: list[CheckoOkved] = Field(default_factory=list)
    ОКОПФ: CheckoClassifier | None = None
    ОКФС: CheckoClassifier | None = None
    ОКОГУ: CheckoClassifier | None = None
    ОКАТО: CheckoClassifier | None = None
    ОКТМО: CheckoClassifier | None = None
    РегФНС: CheckoRegAuthority | None = None
    ТекФНС: CheckoRegAuthority | None = None
    РегПФР: CheckoRegPFR | None = None
    РегФСС: CheckoRegFSS | None = None
    УстКап: CheckoCapital | None = None
    УпрОрг: CheckoUprOrg | None = None
    Руковод: list[CheckoRukovoditel] = Field(default_factory=list)
    Учред: CheckoUchrediteli | None = None
    СвязУпрОрг: list[CheckoSvyazItem] = Field(default_factory=list)
    СвязУчред: list[CheckoSvyazItem] = Field(default_factory=list)
    ДержРеестрАО: CheckoDerzhReestr | None = None
    Лиценз: list[CheckoLicense] = Field(default_factory=list)
    ТоварЗнак: list[CheckoTrademark] = Field(default_factory=list)
    Подразд: CheckoPodrazdel | None = None
    Правопредш: list[CheckoPravopredshestv] = Field(default_factory=list)
    Правопреем: list[CheckoPravopredshestv] = Field(default_factory=list)
    ДатаВып: str = ""
    Контакты: CheckoContactInfo | None = None
    Налоги: CheckoNalogi | None = None
    РМСП: CheckoMSPE | None = None
    ПоддержМСП: list[CheckoMSPSupport] = Field(default_factory=list)
    СЧР: int | None = None
    ЕФРСБ: list[CheckoBankruptcyMsg] = Field(default_factory=list)
    НедобПост: bool = False
    НедобПостЗап: list[CheckoNedobPostZap] = Field(default_factory=list)
    ДисквЛица: bool = False
    МассРуковод: bool = False
    МассУчред: bool = False
    НелегалФин: bool = False
    НелегалФинСтатус: str = ""
    Санкции: bool = False
    СанкцииСтраны: list[str] = Field(default_factory=list)
    СанкцУчр: bool = False


class CheckoCompanyResponse(BaseModel):
    data: CheckoCompanyData | None = None
    source_data: dict[str, Any] | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 2. Entrepreneur (ЕГРИП) ===


class CheckoEntrepreneurStatus(BaseModel):
    ОгрДоступ: bool = False
    Код: str = ""
    Наим: str = ""


class CheckoEntrepreneurPrekrash(BaseModel):
    Дата: str = ""
    Наим: str = ""


class CheckoEntrepreneurData(BaseModel):
    ОГРНИП: str = ""
    ИНН: str = ""
    ОКПО: str = ""
    ДатаРег: str = ""
    ДатаОГРНИП: str = ""
    ФИО: str = ""
    Тип: str = ""
    ТипСокр: str = ""
    Пол: str = ""
    Статус: CheckoEntrepreneurStatus | None = None
    Прекращ: CheckoEntrepreneurPrekrash | None = None
    Регион: CheckoRegion | None = None
    НасПункт: str = ""
    ОКВЭД: CheckoOkved | None = None
    ОКВЭДДоп: list[CheckoOkved] = Field(default_factory=list)
    ОКОПФ: CheckoClassifier | None = None
    ОКФС: CheckoClassifier | None = None
    ОКОГУ: CheckoClassifier | None = None
    ОКАТО: CheckoClassifier | None = None
    ОКТМО: CheckoClassifier | None = None
    РегФНС: CheckoRegAuthority | None = None
    ТекФНС: CheckoRegAuthority | None = None
    РегПФР: CheckoRegPFR | None = None
    РегФСС: CheckoRegFSS | None = None
    СвязРуковод: list[CheckoSvyazItem] = Field(default_factory=list)
    СвязУчред: list[CheckoSvyazItem] = Field(default_factory=list)
    Лиценз: list[CheckoLicense] = Field(default_factory=list)
    ТоварЗнак: list[CheckoTrademark] = Field(default_factory=list)
    ДатаВып: str = ""
    Налоги: dict[str, Any] | None = None
    РМСП: CheckoMSPE | None = None
    ПоддержМСП: list[CheckoMSPSupport] = Field(default_factory=list)
    ЕФРСБ: list[CheckoBankruptcyMsg] = Field(default_factory=list)
    НедобПост: bool = False
    НедобПостЗап: list[CheckoNedobPostZap] = Field(default_factory=list)
    МассРуковод: bool = False
    МассУчред: bool = False


class CheckoEntrepreneurResponse(BaseModel):
    data: CheckoEntrepreneurData | None = None
    source_data: dict[str, Any] | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 3. Person (Физические лица) ===


class CheckoPersonOrgLink(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoPersonIE(BaseModel):
    ОГРНИП: str = ""
    ИНН: str = ""
    ФИО: str = ""
    Тип: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаПрекращ: str = ""
    РегионКод: str = ""
    ОКВЭД: str = ""


class CheckoPersonData(BaseModel):
    ИНН: str = ""
    ФИО: str = ""
    Руковод: list[CheckoPersonOrgLink] = Field(default_factory=list)
    Учред: list[CheckoPersonOrgLink] = Field(default_factory=list)
    ИП: list[CheckoPersonIE] = Field(default_factory=list)
    ТоварЗнак: list[CheckoTrademark] = Field(default_factory=list)
    ЕФРСБ: list[CheckoBankruptcyMsg] = Field(default_factory=list)
    НедобПост: bool = False
    НедобПостЗап: list[CheckoNedobPostZap] = Field(default_factory=list)
    МассРуковод: bool = False
    МассУчред: bool = False
    Санкции: bool = False
    СанкцииСтраны: list[str] = Field(default_factory=list)


class CheckoPersonResponse(BaseModel):
    data: CheckoPersonData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 4. Finances (Финансовая отчетность) ===


class CheckoFinancesCompany(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoFinancesBONalog(BaseModel):
    ID: int = 0
    Отчет: dict[str, str] = Field(default_factory=dict)


class CheckoFinancesResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    data: dict[str, dict[str, Any]] = Field(default_factory=dict)
    bo_nalog_ru: CheckoFinancesBONalog | None = Field(None, alias="bo.nalog.ru")
    meta: CheckoMeta = Field(default_factory=CheckoMeta)

    model_config = {"populate_by_name": True}


# === 5. Reliability (Оценка надежности) ===


class CheckoReliabilityCompany(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoReliabilityEntrepreneur(BaseModel):
    ОГРНИП: str = ""
    ИНН: str = ""
    ФИО: str = ""
    Тип: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаПрекращ: str = ""
    РегионКод: str = ""
    ОКВЭД: str = ""


class CheckoNominalnost(BaseModel):
    Уровень: int = 0
    Наим: str = ""


class CheckoFinRisks(BaseModel):
    Уровень: int = 0
    Наим: str = ""


class CheckoBalance(BaseModel):
    Полож: int = 0
    ТрВним: int = 0
    Негатив: int = 0


class CheckoFactor(BaseModel):
    Код: str = ""
    Тип: str = ""
    Вес: float = 0
    Текст: str = ""


class CheckoReliabilityData(BaseModel):
    Масштаб: int | None = None
    Номинальность: CheckoNominalnost | None = None
    ФинРиски: CheckoFinRisks | None = None
    Баланс: CheckoBalance | None = None
    Факторы: list[CheckoFactor] = Field(default_factory=list)


class CheckoReliabilityResponse(BaseModel):
    company: CheckoReliabilityCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoReliabilityData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 6. Search (Поиск) ===


class CheckoSearchOrgRecord(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoSearchEntRecord(BaseModel):
    ОГРНИП: str = ""
    ИНН: str = ""
    ФИО: str = ""
    Тип: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаПрекращ: str = ""
    РегионКод: str = ""
    ОКВЭД: str = ""


class CheckoSearchData(BaseModel):
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[dict[str, Any]] = Field(default_factory=list)


class CheckoSearchResponse(BaseModel):
    data: CheckoSearchData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 7. Timeline (История событий) ===


class CheckoTimelineEvent(BaseModel):
    Дата: str = ""
    Событие: str = ""


class CheckoTimelineCompany(BaseModel):
    ОГРН: str = ""
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаЛикв: str = ""
    РегионКод: str = ""
    ЮрАдрес: str = ""
    ОКВЭД: str = ""


class CheckoTimelineEntrepreneur(BaseModel):
    ОГРНИП: str = ""
    ИНН: str = ""
    ФИО: str = ""
    Тип: str = ""
    ДатаРег: str = ""
    Статус: str = ""
    ДатаПрекращ: str = ""
    РегионКод: str = ""
    ОКВЭД: str = ""


class CheckoTimelinePerson(BaseModel):
    ИНН: str = ""
    ФИО: str = ""


class CheckoTimelineResponse(BaseModel):
    company: CheckoTimelineCompany | None = None
    entrepreneur: CheckoTimelineEntrepreneur | None = None
    person: CheckoTimelinePerson | None = None
    data: list[CheckoTimelineEvent] = Field(default_factory=list)
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 8. Legal Cases (Арбитражные дела) ===


class CheckoLegalCaseParty(BaseModel):
    ИНН: str = ""
    Наим: str = ""
    Адрес: str = ""


class CheckoLegalCaseRecord(BaseModel):
    Номер: str = ""
    UUID: str = ""
    СтрКАД: str = ""
    Дата: str = ""
    Тип: str = ""
    ПрАктуал: bool = False
    ПрАктив: bool = False
    ДатаСлед: str = ""
    Суд: str = ""
    Ист: list[CheckoLegalCaseParty] = Field(default_factory=list)
    Ответ: list[CheckoLegalCaseParty] = Field(default_factory=list)
    СуммИск: float = 0
    ИсходКод: str = ""
    ИсходТекст: str = ""
    Победитель: str = ""
    ИсходДост: str = ""


class CheckoLegalCasesData(BaseModel):
    ЗапВсего: int = 0
    СтрВсего: int = 0
    СтрТекущ: int = 0
    ОбщСуммИск: float = 0
    Записи: list[CheckoLegalCaseRecord] = Field(default_factory=list)


class CheckoLegalCasesResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoLegalCasesData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 9. Enforcements (Исполнительные производства) ===


class CheckoEnforcementRecord(BaseModel):
    ДолжНаим: str = ""
    ДолжАдрес: str = ""
    ИспПрНомер: str = ""
    ИспПрДата: str = ""
    ИспДокНомер: str = ""
    ИспДокТип: str = ""
    ИспДокДата: str = ""
    ПредмИсп: str = ""
    СудПристНаим: str = ""
    СудПристАдрес: str = ""
    СумДолг: float = 0
    ОстЗадолж: float = 0


class CheckoEnforcementsData(BaseModel):
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[CheckoEnforcementRecord] = Field(default_factory=list)


class CheckoEnforcementsResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    data: CheckoEnforcementsData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 10. Contracts (Госзакупки) ===


class CheckoContractCustomer(BaseModel):
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""


class CheckoContractSupplier(BaseModel):
    ИНН: str = ""
    КПП: str = ""
    НаимСокр: str = ""
    НаимПолн: str = ""
    ФИО: str = ""


class CheckoContractObject(BaseModel):
    Наим: str = ""
    ОКДП: str = ""
    ОКПД: str = ""
    ОКПД2: str = ""


class CheckoContractRecord(BaseModel):
    РегНомер: str = ""
    СтрЕИС: str = ""
    РегионКод: str = ""
    Дата: str = ""
    ДатаИсп: str = ""
    Цена: int = 0
    Заказ: CheckoContractCustomer | None = None
    Постав: list[CheckoContractSupplier] = Field(default_factory=list)
    Объекты: list[CheckoContractObject] = Field(default_factory=list)


class CheckoContractsData(BaseModel):
    ЗапВсего: int = 0
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[CheckoContractRecord] = Field(default_factory=list)


class CheckoContractsResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoContractsData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 11. Fedresurs (Федресурс) ===


class CheckoFedresursRecord(BaseModel):
    GUID: str = ""
    URL: str = ""
    Дата: str = ""
    Тип: str = ""
    ТипНаим: str = ""
    Публикатор: str = ""
    Участники: list[str] = Field(default_factory=list)


class CheckoFedresursData(BaseModel):
    ЗапВсего: int = 0
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[CheckoFedresursRecord] = Field(default_factory=list)


class CheckoFedresursResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoFedresursData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 12. Bankruptcy Messages (ЕФРСБ) ===


class CheckoBankruptcyRecord(BaseModel):
    GUID: str = ""
    URL: str = ""
    Дата: str = ""
    Тип: str = ""
    ТипНаим: str = ""
    НомерДела: str = ""
    Суд: str = ""
    РешенСуда: str = ""


class CheckoBankruptcyData(BaseModel):
    ЗапВсего: int = 0
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[CheckoBankruptcyRecord] = Field(default_factory=list)


class CheckoBankruptcyResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoBankruptcyData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 13. Inspections (Проверки и КНМ) ===


class CheckoInspectionOrgControl(BaseModel):
    ОГРН: str = ""
    Наим: str = ""
    Функ: str = ""


class CheckoInspectionOfficials(BaseModel):
    ФИО: str = ""
    Долж: str = ""


class CheckoInspectionPrescription(BaseModel):
    Код: str = ""
    Текст: str = ""
    Дата: str = ""


class CheckoInspectionViolationCourt(BaseModel):
    Тип: str = ""
    Текст: str = ""


class CheckoInspectionViolation(BaseModel):
    Текст: str = ""
    СудСвед: list[CheckoInspectionViolationCourt] = Field(default_factory=list)
    Предпис: list[CheckoInspectionPrescription] = Field(default_factory=list)


class CheckoInspectionResultInfo(BaseModel):
    Тип: str = ""
    Текст: str = ""


class CheckoInspectionPresentPerson(BaseModel):
    ФИО: str = ""
    Долж: str = ""


class CheckoInspectionResult(BaseModel):
    ДатаАкт: str = ""
    Пред: CheckoInspectionPresentPerson | None = None
    Инфо: list[CheckoInspectionResultInfo] = Field(default_factory=list)
    Наруш: list[CheckoInspectionViolation] = Field(default_factory=list)


class CheckoInspectionObject(BaseModel):
    Адрес: str = ""
    Результ: CheckoInspectionResult | None = None


class CheckoInspectionMeasure(BaseModel):
    Наим: str = ""
    ДатаНач: str = ""
    ДатаОконч: str = ""


class CheckoInspectionRecord(BaseModel):
    Номер: str = ""
    Статус: str = ""
    Заверш: bool = False
    Наруш: bool = False
    ТипРасп: str = ""
    ТипПров: str = ""
    КлассРиск: str = ""
    ДатаНач: str = ""
    ДатаОконч: str = ""
    Цель: str = ""
    Обосн: str = ""
    ОргКонтр: CheckoInspectionOrgControl | None = None
    Треб: list[str] = Field(default_factory=list)
    ДолжЛица: CheckoInspectionOfficials | None = None
    Объекты: list[CheckoInspectionObject] = Field(default_factory=list)
    Меропр: list[CheckoInspectionMeasure] = Field(default_factory=list)


class CheckoInspectionsData(BaseModel):
    ЗапВсего: int = 0
    СтрВсего: int = 0
    СтрТекущ: int = 0
    Записи: list[CheckoInspectionRecord] = Field(default_factory=list)


class CheckoInspectionsResponse(BaseModel):
    company: CheckoFinancesCompany | None = None
    entrepreneur: CheckoReliabilityEntrepreneur | None = None
    data: CheckoInspectionsData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === 14. Bank (Банки) ===


class CheckoBankKorSchet(BaseModel):
    Номер: str = ""
    Дата: str = ""


class CheckoBankAccount(BaseModel):
    Номер: str = ""
    Дата: str = ""
    Тип: str = ""


class CheckoBankData(BaseModel):
    БИК: str = ""
    Наим: str = ""
    НаимАнгл: str = ""
    Адрес: str = ""
    Тип: str = ""
    КорСчет: CheckoBankKorSchet | None = None
    Счета: list[CheckoBankAccount] = Field(default_factory=list)


class CheckoBankResponse(BaseModel):
    data: CheckoBankData | None = None
    meta: CheckoMeta = Field(default_factory=CheckoMeta)


# === Full Check (комплексная проверка) ===


class CheckoFullCheckResult(BaseModel):
    """Результат комплексной проверки — агрегация 7 рисковых методов."""
    company: CheckoCompanyResponse | None = None
    reliability: CheckoReliabilityResponse | None = None
    legal_cases: CheckoLegalCasesResponse | None = None
    enforcements: CheckoEnforcementsResponse | None = None
    bankruptcy: CheckoBankruptcyResponse | None = None
    fedresurs: CheckoFedresursResponse | None = None
    inspections: CheckoInspectionsResponse | None = None
    errors: list[str] = Field(default_factory=list)