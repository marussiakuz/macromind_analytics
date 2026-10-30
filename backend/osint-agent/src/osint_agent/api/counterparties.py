"""Counterparty verification through Checko."""

from fastapi import APIRouter, HTTPException

from osint_agent.connectors.checko import CheckoConnector
from osint_agent.connectors.egrul import validate_inn
from osint_agent.models import ConnectorQuery

router = APIRouter(prefix="/api/v1/counterparties", tags=["counterparties"])


@router.get("/{inn}")
async def check_counterparty(inn: str, include_reliability: bool = False):
    if not inn.isascii() or not inn.isdigit() or not validate_inn(inn):
        raise HTTPException(status_code=400, detail="Некорректный ИНН")
    connector = CheckoConnector()
    try:
        result = await connector.execute(
            ConnectorQuery(query_type="company_legal", params={"inn": inn})
        )
        if not result.success:
            raise HTTPException(status_code=502, detail=result.error)
        response = {"company": result.data, "source": result.source}
        if include_reliability:
            assessment = await connector.execute(
                ConnectorQuery(query_type="counterparty_reliability", params={"inn": inn})
            )
            response["reliability"] = {
                "success": assessment.success,
                "data": assessment.data,
                "error": assessment.error,
                "source": assessment.source,
            }
        return response
    finally:
        await connector.close()
