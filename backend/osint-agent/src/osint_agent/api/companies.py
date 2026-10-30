"""Company/entrepreneur search and finances through Checko (search.md, finances.md)."""

from fastapi import APIRouter, HTTPException, Query

from osint_agent.connectors.checko import SEARCH_BY, CheckoConnector
from osint_agent.connectors.egrul import validate_inn
from osint_agent.models import ConnectorQuery

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])

ALLOWED_OBJ = {"org", "ent"}
# name / founder / leader need 4+ chars; other types have their own rules
_NAME_LIKE = {"name", "founder-name", "leader-name"}
# ОКВЭД-2: 62 | 62.0 | 62.01 | 62.01.1 | 62.01.11
_OKVED_RE = r"^\d{2}(\.\d{1,3}){0,3}$"


@router.get("/search")
async def search_companies(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    by: str = Query("name", description="Тип поиска: name, founder-name, leader-name, okved, reg-date, upd-date, phone, email"),
    obj: str = Query("org", description="org — организации, ent — ИП"),
    region: str | None = None,
    okved: str | None = None,
    opf: str | None = None,
    active: bool | None = None,
    codes: str | None = None,
    limit: int | None = Query(None, ge=1, le=100),
    page: int | None = Query(None, ge=1),
):
    """Поиск организаций и ИП по названию, ФИО, ОКВЭД, датам, телефону, email."""
    if by not in SEARCH_BY:
        raise HTTPException(status_code=400, detail="Некорректный тип поиска")
    if obj not in ALLOWED_OBJ:
        raise HTTPException(status_code=400, detail="Некорректный тип объекта")
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Пустой поисковый запрос")
    if by in _NAME_LIKE and len(query) < 4:
        raise HTTPException(
            status_code=400,
            detail="Для поиска по наименованию/ФИО нужно минимум 4 символа",
        )
    if by == "okved":
        import re
        if not re.match(_OKVED_RE, query):
            raise HTTPException(status_code=400, detail="Некорректный код ОКВЭД")
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(
                query_type="company_search",
                params={
                    "by": by,
                    "obj": obj,
                    "query": query,
                    "region": region,
                    "okved": okved,
                    "opf": opf,
                    "active": active,
                    "codes": codes,
                    "limit": limit,
                    "page": page,
                },
            )
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        return result.data
    finally:
        await connector.close()


@router.get("/{inn}/finances")
async def company_finances(inn: str):
    """Финансовая отчетность организации (finances.md): выручка 2110, чистая прибыль 2400."""
    if not inn.isascii() or not inn.isdigit() or not validate_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    if len(inn) != 10:
        raise HTTPException(
            status_code=400,
            detail="Финансовая отчетность доступна только для организаций (ИНН 10 цифр)",
        )
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(query_type="company_finances", params={"inn": inn})
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        return {"finances": result.data, "source": result.source}
    finally:
        await connector.close()


@router.get("/{inn}/timeline")
async def company_timeline(inn: str):
    """История событий и изменений контрагента (timeline.md)."""
    if not inn.isascii() or not inn.isdigit() or not validate_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(query_type="company_timeline", params={"inn": inn})
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        return {"timeline": result.data, "source": result.source}
    finally:
        await connector.close()


REGISTRY_METHODS = {
    "legal-cases",
    "enforcements",
    "contracts",
    "fedresurs",
    "bankruptcy-messages",
    "inspections",
}


@router.get("/{inn}/registry/{method}")
async def company_registry(
    inn: str,
    method: str,
    law: str | None = Query(None, description="Для contracts: 44, 94, 223"),
    role: str | None = None,
    sort: str | None = None,
    limit: int | None = Query(None, ge=1, le=100),
    page: int | None = Query(None, ge=1),
):
    """Списочные реестры: legal-cases, enforcements, contracts, fedresurs, bankruptcy-messages, inspections."""
    if not inn.isascii() or not inn.isdigit() or not validate_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    if method not in REGISTRY_METHODS:
        raise HTTPException(status_code=400, detail="Некорректный метод реестра")
    if method == "contracts" and not law:
        raise HTTPException(status_code=400, detail="Для contracts укажите law (44, 94 или 223)")
    if method == "contracts" and law not in {"44", "94", "223"}:
        raise HTTPException(status_code=400, detail="law должен быть 44, 94 или 223")
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(
                query_type="company_registry",
                params={
                    "method": method,
                    "inn": inn,
                    "law": law,
                    "role": role,
                    "sort": sort,
                    "limit": limit,
                    "page": page,
                },
            )
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        return {"registry": result.data, "source": result.source}
    finally:
        await connector.close()
