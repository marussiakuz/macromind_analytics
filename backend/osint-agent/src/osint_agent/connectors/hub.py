"""DataConnectorHub — unified entry point for all external API connectors."""

from typing import Any

from osint_agent.connectors.base import BaseConnector
from osint_agent.models import ConnectorQuery, ConnectorResult
from osint_agent.utils import get_logger

logger = get_logger(__name__)


class DataConnectorHub:
    """Unified entry point for all external API connectors.

    Features:
    - Routing by data type
    - Fallback chains
    - Circuit breaker (TODO)
    - Health monitoring
    """

    # Fallback chains by data type
    FALLBACK_CHAINS: dict[str, list[str]] = {
        "company_legal": ["checko", "egrul", "spark", "kontur"],
        "counterparty_reliability": ["checko"],
        "court_cases": ["kad", "cached_kad"],
        "sanctions": ["live_sanctions", "local_mirror"],
        "news": ["tavily", "rss"],
        "tax_debt": ["fns_tax"],
        "bailiff": ["fssp"],
        "tenders": ["tenders"],
        "social": ["vk", "linkedin", "facebook"],
        "whois": ["whois"],
        "pep": ["pep"],
    }

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """Register a connector."""
        self._connectors[connector.name] = connector
        logger.info("connector_registered", name=connector.name)

    def get_connector(self, name: str) -> BaseConnector | None:
        """Get connector by name."""
        return self._connectors.get(name)

    async def fetch(
        self,
        query_type: str,
        params: dict[str, Any],
        priority: str = "normal",
    ) -> ConnectorResult:
        """Fetch data using fallback chain.

        Args:
            query_type: Type of data to fetch (e.g., "company_legal", "sanctions")
            params: Query parameters
            priority: Query priority ("high", "normal", "low")

        Returns:
            ConnectorResult from the first successful connector
        """
        chain = self.FALLBACK_CHAINS.get(query_type, [query_type])

        for connector_name in chain:
            connector = self._connectors.get(connector_name)
            if not connector:
                logger.debug(
                    "connector_not_found",
                    name=connector_name,
                    query_type=query_type,
                )
                continue

            query = ConnectorQuery(
                query_type=query_type,
                params=params,
                priority=priority,
            )

            result = await connector.execute(query)

            if result.success:
                logger.info(
                    "fetch_success",
                    connector=connector_name,
                    query_type=query_type,
                )
                return result

            logger.warning(
                "fetch_failed",
                connector=connector_name,
                query_type=query_type,
                error=result.error,
            )

        # All connectors failed
        logger.error(
            "all_connectors_failed",
            query_type=query_type,
            chain=chain,
        )
        return ConnectorResult(
            success=False,
            source="hub",
            error=f"All connectors failed for {query_type}: {chain}",
        )

    async def health_check(self) -> dict[str, bool]:
        """Check health of all registered connectors."""
        results = {}
        for name, connector in self._connectors.items():
            try:
                results[name] = await connector.health_check()
            except Exception:
                results[name] = False
        return results

    async def close(self) -> None:
        """Close all connectors."""
        for connector in self._connectors.values():
            await connector.close()


# Global instance
hub = DataConnectorHub()
