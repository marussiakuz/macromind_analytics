"""DataConnectorHub — unified entry point for all external API connectors."""

from typing import Any

from person_osint.connectors.base import BaseConnector
from person_osint.models import ConnectorQuery, ConnectorResult


class DataConnectorHub:
    """Unified entry point for all external API connectors.

    Features:
    - Routing by data type
    - Fallback chains
    - Health monitoring
    """

    FALLBACK_CHAINS: dict[str, list[str]] = {
        "linkedin": ["linkedin"],
        "habr": ["habr"],
        "vc": ["vc"],
        "github": ["github"],
        "scholar": ["scholar"],
        "books": ["books"],
        "medium": ["medium"],
        "vk": ["vk"],
        "odnoklassniki": ["odnoklassniki"],
        "telegram": ["telegram"],
        "yandex_people": ["yandex_people"],
        "pipl": ["pipl"],
        "google_search": ["google_search"],
        "sanctions": ["sanctions"],
        "courts": ["courts"],
        "fssp": ["fssp"],
        "pep": ["pep"],
        "news": ["news"],
        "username_scan": ["username_scan"],
        "checko": ["checko"],
    }

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """Register a connector."""
        self._connectors[connector.name] = connector

    def get_connector(self, name: str) -> BaseConnector | None:
        """Get connector by name."""
        return self._connectors.get(name)

    async def fetch(
        self,
        query_type: str,
        params: dict[str, Any],
        priority: str = "normal",
    ) -> ConnectorResult:
        """Fetch data using fallback chain."""
        chain = self.FALLBACK_CHAINS.get(query_type, [query_type])

        for connector_name in chain:
            connector = self._connectors.get(connector_name)
            if not connector:
                continue

            query = ConnectorQuery(
                query_type=query_type,
                params=params,
                priority=priority,
            )

            result = await connector.execute(query)

            if result.success:
                return result

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
