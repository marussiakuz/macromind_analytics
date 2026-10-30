"""API endpoints для Checko — проверка контрагентов."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from person_osint.connectors.checko import CheckoConnector

router = APIRouter(prefix="/api/v1/checko", tags=["checko"])

_connector: CheckoConnector | None = None


def _get_connector() -> CheckoConnector:
    global _connector
    if _connector is None:
        _connector = CheckoConnector()
    return _connector


# === Request models ===


class CompanyRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    okpo: str | None = None
    source: bool = False


class EntrepreneurRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    okpo: str | None = None
    source: bool = False


class PersonRequest(BaseModel):
    inn: str


class FinancesRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    extended: bool = False


class ReliabilityRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None


class SearchRequest(BaseModel):
    by: str  # name, founder-name, leader-name, okved, reg-date, upd-date, phone, email
    obj: str  # org, ent
    query: str
    region: str | None = None
    okved: str | None = None
    opf: str | None = None
    active: bool | None = None
    codes: str | None = None
    limit: int | None = None
    page: int | None = None


class TimelineRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None


class LegalCasesRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    role: str | None = None  # plaintiff, defendant
    actual: bool | None = None
    active: bool | None = None
    date_from: str | None = None
    date_to: str | None = None
    claim_amount_from: float | None = None
    claim_amount_to: float | None = None
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class EnforcementsRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class ContractsRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    law: str  # 44, 94, 223
    role: str | None = None  # customer, supplier
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class FedresursRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    type: str | None = None
    role: str | None = None  # all, publisher
    date_from: str | None = None
    date_to: str | None = None
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class BankruptcyRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class InspectionsRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    limit: int | None = None
    page: int | None = None
    sort: str | None = None


class BankRequest(BaseModel):
    bic: str


class FullCheckRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None


# === Helper ===

_MISSING_KEY_MESSAGE = "Проверка недоступна: ключ Checko не настроен"


def _raise_connector_error(result) -> None:
    """Map connector error codes to HTTP status (MIMO rules §6)."""
    code = getattr(result, "error_code", None)
    if code == "missing_api_key":
        raise HTTPException(status_code=503, detail=result.error or _MISSING_KEY_MESSAGE)
    raise HTTPException(status_code=502, detail=result.error or "Checko API error")


async def _call(action: str, params: dict[str, Any]) -> dict[str, Any]:
    connector = _get_connector()
    from person_osint.models import ConnectorQuery
    query = ConnectorQuery(query_type="checko", params={"action": action, **params})
    result = await connector.execute(query)
    if not result.success:
        _raise_connector_error(result)
    return result.data


# === Endpoints ===

@router.post("/company")
async def checko_company(request: CompanyRequest) -> dict[str, Any]:
    """Проверка организации по ИНН/ОГРН/ОКПО (ЕГРЮЛ)."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("company", params)


@router.post("/entrepreneur")
async def checko_entrepreneur(request: EntrepreneurRequest) -> dict[str, Any]:
    """Проверка ИП по ИНН/ОГРНИП/ОКПО (ЕГРИП)."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("entrepreneur", params)


@router.post("/person")
async def checko_person(request: PersonRequest) -> dict[str, Any]:
    """Проверка физлица по ИНН."""
    return await _call("person", {"inn": request.inn})


@router.post("/finances")
async def checko_finances(request: FinancesRequest) -> dict[str, Any]:
    """Финансовая отчетность организации."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("finances", params)


@router.post("/reliability")
async def checko_reliability(request: ReliabilityRequest) -> dict[str, Any]:
    """Оценка надежности контрагента."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("reliability", params)


@router.post("/search")
async def checko_search(request: SearchRequest) -> dict[str, Any]:
    """Поиск организаций и ИП."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("search", params)


@router.post("/timeline")
async def checko_timeline(request: TimelineRequest) -> dict[str, Any]:
    """История событий и изменений."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("timeline", params)


@router.post("/legal-cases")
async def checko_legal_cases(request: LegalCasesRequest) -> dict[str, Any]:
    """Арбитражные дела."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("legal-cases", params)


@router.post("/enforcements")
async def checko_enforcements(request: EnforcementsRequest) -> dict[str, Any]:
    """Исполнительные производства (ФССП)."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("enforcements", params)


@router.post("/contracts")
async def checko_contracts(request: ContractsRequest) -> dict[str, Any]:
    """Госзакупки (44-ФЗ, 94-ФЗ, 223-ФЗ)."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("contracts", params)


@router.post("/fedresurs")
async def checko_fedresurs(request: FedresursRequest) -> dict[str, Any]:
    """Сообщения Федресурса."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("fedresurs", params)


@router.post("/bankruptcy-messages")
async def checko_bankruptcy(request: BankruptcyRequest) -> dict[str, Any]:
    """Записи ЕФРСБ (банкротства)."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("bankruptcy-messages", params)


@router.post("/inspections")
async def checko_inspections(request: InspectionsRequest) -> dict[str, Any]:
    """Проверки и КНМ."""
    params = request.model_dump(exclude_none=True, exclude_defaults=True)
    return await _call("inspections", params)


@router.post("/bank")
async def checko_bank(request: BankRequest) -> dict[str, Any]:
    """Информация о банке по БИК."""
    return await _call("bank", {"bic": request.bic})


@router.post("/full-check")
async def checko_full_check(request: FullCheckRequest) -> dict[str, Any]:
    """Комплексная проверка — 7 рисковых методов параллельно.

    Выполняет: company, reliability, legal-cases, enforcements,
    bankruptcy-messages, fedresurs, inspections.
    """
    connector = _get_connector()
    params = request.model_dump(exclude_none=True)
    results = await connector.full_check(params)

    # Missing key is a whole-request configuration failure, not a partial 200 report.
    if set(results.keys()) == {"error"} and results["error"].error_code == "missing_api_key":
        raise HTTPException(status_code=503, detail=results["error"].error or _MISSING_KEY_MESSAGE)

    output: dict[str, Any] = {}
    errors: list[str] = []
    for name, result in results.items():
        if result.success:
            output[name] = result.data
        else:
            output[name] = None
            errors.append(f"{name}: {result.error}")

    output["_errors"] = errors
    output["_status"] = "ok" if not errors else "partial"
    return output