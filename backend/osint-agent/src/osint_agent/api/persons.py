"""Person business-links verification through Checko (person.md)."""

from fastapi import APIRouter, HTTPException

from osint_agent.connectors.checko import CheckoConnector
from osint_agent.connectors.egrul import validate_inn
from osint_agent.models import ConnectorQuery

router = APIRouter(prefix="/api/v1/persons", tags=["persons"])


@router.get("/{inn}")
async def check_person(inn: str):
    """Деловые связи физлица по ИНН: организации, ИП, факторы риска."""
    if not inn.isascii() or not inn.isdigit() or len(inn) != 12 or not validate_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН физлица")
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(query_type="person_legal", params={"inn": inn})
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        return {"person": result.data, "source": result.source}
    finally:
        await connector.close()
