"""Graph API — эндпоинт для получения графа связей компании.

GET /api/v1/graph/{inn} — возвращает граф в формате vis.js.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.connectors.egrul import MockEGRULConnector
from osint_agent.connectors.whois import WhoisConnector, MockWhoisConnector
from osint_agent.connectors.dns import DNSConnector, MockDNSConnector
from osint_agent.connectors.shodan import ShodanConnector, MockShodanConnector
from osint_agent.connectors.document import DocumentConnector, MockDocumentConnector
from osint_agent.connectors.checko import CheckoConnector
from osint_agent.config import settings
from osint_agent.graph.builder import CompanyGraphBuilder
from osint_agent.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


# --- Response models ---

class GraphStats(BaseModel):
    """Статистика графа."""
    nodes: int
    edges: int


class GraphResponse(BaseModel):
    """Ответ с графом связей компании."""
    company_inn: str
    company_name: str
    graph: dict  # vis.js format: {nodes: [...], edges: [...]}
    stats: GraphStats
    source: str = ""
    source_status: str = "not_checked"
    is_demo: bool = False


# --- Hub setup ---

def _build_hub() -> DataConnectorHub:
    """Use real sources by default; test data requires DEMO_MODE=true."""
    hub = DataConnectorHub()
    hub.register(MockEGRULConnector() if settings.demo_mode else CheckoConnector())
    hub.register(MockWhoisConnector() if settings.demo_mode else WhoisConnector())
    hub.register(MockDNSConnector() if settings.demo_mode else DNSConnector())
    hub.register(MockShodanConnector() if settings.demo_mode else ShodanConnector())
    hub.register(MockDocumentConnector() if settings.demo_mode else DocumentConnector())
    return hub


# --- Endpoints ---

@router.get("/{inn}", response_model=GraphResponse)
async def get_company_graph(
    inn: str,
    website: str | None = Query(None, description="Сайт компании"),
):
    """Получить граф связей компании по ИНН.

    Args:
        inn: ИНН компании (10 цифр)
        website: Сайт компании (опционально)

    Returns:
        GraphResponse с графом в формате vis.js
    """
    # Validate INN format
    if not inn.isdigit() or len(inn) not in (10, 12):
        raise HTTPException(
            status_code=400,
            detail="ИНН должен содержать 10 или 12 цифр",
        )

    hub = _build_hub()

    try:
        # Fetch company name from EGRUL (may fail for unknown INNs — that's OK)
        egrul_result = await hub.fetch("company_legal", {"inn": inn})

        if egrul_result.success:
            company_name = egrul_result.data.get("name", f"Компания {inn}")
        else:
            company_name = f"Компания ИНН {inn}"

        # Build graph (works even without EGRUL data — builds from website)
        builder = CompanyGraphBuilder(hub)
        graph = await builder.build(
            company_name=company_name,
            inn=inn,
            website=website,
            company_result=egrul_result,
        )

        # Export to vis.js format
        vis_data = graph.to_vis_js()
        stats = graph.get_stats()

        logger.info(
            "graph_api_request",
            inn=inn,
            nodes=stats["nodes"],
            edges=stats["edges"],
        )

        return GraphResponse(
            company_inn=inn,
            company_name=company_name,
            graph=vis_data,
            stats=GraphStats(**stats),
            source=egrul_result.source,
            source_status="ok" if egrul_result.success else "not_checked",
            is_demo=settings.demo_mode or ":mock" in egrul_result.source,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("graph_api_error", inn=inn, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка построения графа: {str(e)}",
        )
    finally:
        await hub.close()
