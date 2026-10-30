"""End-to-end Stage E: ingest → retrieve → bridge market summary."""

from __future__ import annotations

import os
import uuid

import pytest

from osint_agent.knowledge.bridge import KnowledgeBridge
from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.ingestion import Ingester
from osint_agent.knowledge.pg_repository import KnowledgePgRepository
from osint_agent.knowledge.retrieval import EvidenceRetriever
from osint_agent.knowledge.signals import (
    HypothesisInput,
    SignalEventInput,
    WeakSignalService,
)

DSN = os.environ.get(
    "KNOWLEDGE_DATABASE_URL",
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
)


@pytest.fixture
def repo():
    r = KnowledgePgRepository(DSN, application_name="osint-stage-e2e")
    try:
        r.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"knowledge PG unavailable: {exc}")
    yield r
    r.close()


def test_three_modules_share_corpus(repo, tmp_path):
    """Legal entity + market + weak signals reuse one store (Stage E result)."""
    ws = f"e2e-se-{uuid.uuid4().hex[:8]}"
    store = ObjectStore(tmp_path / "obj")
    ing = Ingester(repo, store)

    # 1) shared document ingestion (same source for all modules)
    text = (
        "ООО Ромашка, ИНН 7701. Объем рынка RPA 12 млрд руб. "
        "Запущена платформа роботизации. Закупка автоматизации."
    )
    res = ing.ingest_bytes(
        text.encode(), source_type="file", title="Отраслевой обзор",
        mime_type="text/plain", filename="overview.txt", workspace_id=ws,
    )
    assert res.chunk_ids

    # 2) market bridge attaches evidence_refs pointing at same workspace
    br = KnowledgeBridge(repo)
    out = br.persist_market_evidence(
        {
            "company": {"name": "ООО Ромашка", "inn": "7701"},
            "evidence_refs": [{
                "id": "yandex:1", "type": "web_snippet",
                "title": "Обзор RPA", "quote": "Объем рынка RPA 12 млрд руб",
                "url": "https://ex.ru/rpa",
            }],
            "related_organizations": [{"role": "customer", "name": "Госзаказчик"}],
        },
        workspace_id=ws,
        inn="7701",
    )
    assert out["evidence_stored"] == 1

    # 3) retrieval finds the shared corpus
    ret = EvidenceRetriever(repo, embed_fn=None)
    found = ret.retrieve("Объем рынка RPA", workspace_id=ws, mode="text")
    assert found.items
    assert any("RPA" in (i.excerpt or "") or "RPA" in (i.title or "") for i in found.items)

    # 4) weak signals on the same workspace
    svc = WeakSignalService(repo)
    ev = svc.record_event(
        SignalEventInput(
            event_type="product_launch", subject="Запуск платформы роботизации",
            event_at=None, workspace_id=ws,
            source_document_id=res.document_id,
        )
    )
    assert ev["id"]
    hyp = svc.form_hypothesis(
        HypothesisInput(
            statement="Появились признаки активности в RPA",
            event_ids=[ev["id"]],
            workspace_id=ws,
            limitations=["мало источников"],
        )
    )
    assert hyp["statement"]
    assert hyp["limitations"]

    # 5) access isolation: other workspace does not see this corpus
    other = f"other-{ws}"
    empty = ret.retrieve("Объем рынка RPA", workspace_id=other, mode="text")
    assert empty.items == []
