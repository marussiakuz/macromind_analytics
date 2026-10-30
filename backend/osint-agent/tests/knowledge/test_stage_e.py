"""Stage E tests: bridge + weak signals (Task2 §9, §11)."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest

from osint_agent.knowledge.bridge import KnowledgeBridge
from osint_agent.knowledge.pg_repository import KnowledgePgRepository
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
    r = KnowledgePgRepository(DSN, application_name="osint-stage-e-tests")
    try:
        r.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"knowledge PG unavailable: {exc}")
    yield r
    r.close()


@pytest.fixture
def ws():
    return f"se-{uuid.uuid4().hex[:12]}"


def test_bridge_persists_market_evidence(repo, ws):
    br = KnowledgeBridge(repo)
    summary = {
        "company": {"name": "ООО Ромашка", "inn": "7701"},
        "evidence_refs": [
            {
                "id": "yandex:abc",
                "type": "web_snippet",
                "source_id": "yandex_search",
                "title": "Рынок RPA",
                "url": "https://example.org/rpa",
                "quote": "Объем рынка 12 млрд",
                "locator": "search_result[0]",
                "completeness": "snippet_only",
            }
        ],
        "related_organizations": [
            {"role": "customer", "name": "Заказчик-1", "evidence_ids": ["yandex:abc"]}
        ],
    }
    out = br.persist_market_evidence(summary, workspace_id=ws, inn="7701")
    assert out["entity_id"]
    assert out["evidence_stored"] == 1
    # snippet is not upgraded to fact
    ev = repo.list_evidence(workspace_id=ws)
    assert ev and ev[0]["claim_type"] == "unverified_snippet"
    assert ev[0]["verification_status"] == "unreviewed"


def test_llm_claim_is_interpretation_not_fact(repo, ws):
    br = KnowledgeBridge(repo)
    eid = br.upsert_company_entity(name="X", inn="1", workspace_id=ws)
    cid = br.persist_llm_claim(
        {"text": "Рынок растет"}, entity_id=eid, workspace_id=ws
    )
    assert cid
    row = [r for r in repo.list_evidence(workspace_id=ws) if str(r["id"]) == cid][0]
    assert row["claim_type"] == "interpretation"


def test_signal_reprint_does_not_inflate_independence(repo, ws):
    svc = WeakSignalService(repo)
    primary = svc.record_event(
        SignalEventInput(
            event_type="product_launch",
            subject="Запуск RPA-платформы",
            technology="RPA",
            event_at=date(2026, 10, 1),
            source_document_id="doc-1",
            workspace_id=ws,
        )
    )
    assert primary["independent_sources"] == 1
    # 10 reprints of the same event
    for i in range(10):
        svc.record_reprint(
            SignalEventInput(
                event_type="product_launch",
                subject="Запуск RPA-платформы",
                technology="RPA",
                event_at=date(2026, 10, 1),
                source_document_id=f"doc-reprint-{i}",
                workspace_id=ws,
            ),
            primary_event_id=primary["id"],
        )
    events = svc.list_events(workspace_id=ws)
    assert len(events) == 1
    assert events[0]["independent_sources"] == 1  # R15


def test_independent_source_does_increment(repo, ws):
    svc = WeakSignalService(repo)
    a = svc.record_event(
        SignalEventInput(
            event_type="trial", subject="Испытания X", technology="AI",
            event_at=date(2026, 10, 1), source_document_id="d1", workspace_id=ws,
        )
    )
    b = svc.record_event(
        SignalEventInput(
            event_type="trial", subject="Испытания X", technology="AI",
            event_at=date(2026, 10, 1), source_document_id="d2", workspace_id=ws,
        )
    )
    assert a["id"] == b["id"]
    assert b["independent_sources"] == 2


def test_hypothesis_zero_baseline_no_infinite_growth(repo, ws):
    svc = WeakSignalService(repo)
    # 3 events in window, 0 in baseline
    today = date.today()
    for i in range(3):
        svc.record_event(
            SignalEventInput(
                event_type="procurement", subject=f"Закупка {i}",
                event_at=today - timedelta(days=2), workspace_id=ws,
            )
        )
    h = svc.form_hypothesis(
        HypothesisInput(
            statement="За период появились закупки",
            workspace_id=ws,
            window_start=today - timedelta(days=7),
            window_end=today,
            baseline_start=today - timedelta(days=90),
            baseline_end=today - timedelta(days=7),
        )
    )
    assert h["status"] == "needs_more_data"
    assert h["coverage_limited"] is True
    lim = " ".join(h["limitations"])
    assert "нулев" in lim.lower() or "0" in lim
    assert "inf" not in lim.lower()
    assert "%" not in lim or "не считаются" in lim


def test_research_binding_links_modules(repo, ws):
    br = KnowledgeBridge(repo)
    vid = repo.save_analysis_version(
        version=1, status="done", summary={"ok": True}, legal_entity_inn="7701"
    )
    bid = br.bind_research(
        legal_entity_inn="7701",
        project_ref="proj-1",
        analysis_version_id=vid,
        workspace_id=ws,
    )
    assert bid
