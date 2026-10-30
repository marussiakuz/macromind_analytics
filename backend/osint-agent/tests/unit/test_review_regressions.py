from unittest.mock import AsyncMock

import pytest

from osint_agent.connectors.base import BaseConnector
from osint_agent.connectors.document import DocumentConnector
from osint_agent.connectors.hub import DataConnectorHub
from osint_agent.graph.builder import CompanyGraphBuilder


@pytest.mark.asyncio
async def test_connector_exception_preserves_fallback(monkeypatch):
    class Failing(BaseConnector):
        name = "egrul"
        rate_limit = 100

        async def fetch(self, query):
            raise RuntimeError("provider unavailable")

        async def health_check(self):
            return True

    from osint_agent.connectors.egrul import MockEGRULConnector

    fallback = MockEGRULConnector()
    monkeypatch.setattr("osint_agent.connectors.base.cache.get", AsyncMock(return_value=None))
    monkeypatch.setattr("osint_agent.connectors.base.cache.set", AsyncMock())
    monkeypatch.setattr("osint_agent.connectors.base.rate_limiter.wait", AsyncMock())
    log = AsyncMock()
    monkeypatch.setattr("osint_agent.connectors.base.audit_log.log", log)
    hub = DataConnectorHub()
    hub.register(Failing())
    hub._connectors["spark"] = fallback
    result = await hub.fetch("company_legal", {"inn": "7701234567"})
    assert result.success
    assert log.await_args_list[0].kwargs["error"] == "provider unavailable"
    assert log.await_args_list[0].kwargs["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_real_document_contacts_reach_graph(tmp_path, monkeypatch):
    from docx import Document

    path = tmp_path / "contacts.docx"
    document = Document()
    document.add_paragraph("Email: review@example.com Phone: +7 (999) 123-45-67")
    document.save(path)
    monkeypatch.setattr("osint_agent.connectors.base.rate_limiter.wait", AsyncMock())
    monkeypatch.setattr("osint_agent.connectors.base.cache.get", AsyncMock(return_value=None))
    hub = DataConnectorHub()
    hub.register(DocumentConnector())
    graph = await CompanyGraphBuilder(hub).build("Test", "7701234567", documents=[str(path)])
    assert any(n.type == "email" and n.label == "review@example.com" for n in graph.nodes.values())
    assert any(n.type == "phone" for n in graph.nodes.values())
