"""Tests: provenance publisher/aggregator, dual metrics, scheduler budget."""

from __future__ import annotations

import time

from osint_agent.knowledge.discovery.provenance import classify_url, provenance_meta
from osint_agent.knowledge.discovery.quality_metrics import evaluate_retrieval_vs_answer
from osint_agent.knowledge.discovery.queries import ProductProfile
from osint_agent.knowledge.discovery.scheduler import (
    DiscoveryBudget,
    DiscoveryScheduler,
    SchedulerState,
)


def test_provenance_publisher_with_body_parsed():
    body = (
        "Методика исследования. Объем рынка RPA в России составил 12,4 млрд рублей. "
        "CAGR 22%. Прогноз на 2026 год — 15,1 млрд. " + ("Детали раздела. " * 40)
    )
    p = classify_url("https://research.example/rpa-2025", title="Рынок RPA исследование",
                     body=body)
    assert p.kind == "publisher"
    assert p.primary_parsed is True
    assert p.supports_claim is True
    meta = provenance_meta(p)
    assert meta["primary_parsed"] and meta["supports_claim"]


def test_provenance_aggregator_not_parsed():
    p = classify_url(
        "https://www.researchandmarkets.com/reports/123",
        title="RPA Market Report",
        body="Buy now. Request sample. Price from $4999.",
    )
    assert p.kind == "aggregator"
    assert p.primary_parsed is False
    assert p.supports_claim is False


def test_provenance_ad_landing_no_body():
    p = classify_url("https://vendor.example/pricing", title="Pricing",
                     body="Buy now request sample")
    assert p.kind == "ad_landing"
    assert p.supports_claim is False


def test_dual_metrics_empty_positive_is_miss():
    class R:
        items = []
        empty_reason = "no_evidence_in_allowed_corpus"
        limitations = []

    def retrieve_fn(q):
        return R()

    def answer_fn(q, res):
        return "Нет данных. [src]"

    out = evaluate_retrieval_vs_answer(
        [{"id": "q1", "question": "x", "answerable": True, "relevant_titles": ["Doc"],
          "forbidden_claims": ["1 млрд"]}],
        retrieve_fn=retrieve_fn,
        answer_fn=answer_fn,
    )
    assert out.retrieval[0].hit is False
    assert out.retrieval[0].latency_ms >= 0
    assert out.answers[0].has_citation is True
    assert out.answers[0].false_claim_suspected is False
    s = out.summary()
    assert s["retrieval"]["hit_rate"] == 0.0
    assert s["answer"]["citation_rate"] == 1.0


def test_dual_metrics_false_claim_detected():
    class Item:
        title = "Doc"
        excerpt = "ok"
        document_id = "d1"
        evidence_id = "e1"

    class R:
        items = [Item()]
        empty_reason = None
        limitations = []

    out = evaluate_retrieval_vs_answer(
        [{"id": "q", "question": "x", "answerable": True, "relevant_ids": ["d1"],
          "forbidden_claims": ["999 млрд"]}],
        retrieve_fn=lambda q: R(),
        answer_fn=lambda q, r: "Выручка 999 млрд",
    )
    assert out.retrieval[0].hit is True
    assert out.answers[0].false_claim_suspected is True


def test_scheduler_budget_and_interval():
    calls = {"n": 0}

    class FakeRepo:
        def close(self):
            pass

    async def fake_discover(*a, **k):
        from osint_agent.knowledge.discovery.pipeline import DiscoveryResult
        calls["n"] += 1
        return DiscoveryResult(ingested=1)

    import osint_agent.knowledge.discovery.scheduler as sch

    async def run():
        profiles = [ProductProfile(product="RPA")]
        sched = DiscoveryScheduler(
            profiles=profiles,
            repo_factory=lambda: FakeRepo(),
            workspace_id="ws",
            budget=DiscoveryBudget(max_cycles_per_day=2, min_interval_seconds=3600),
            state=SchedulerState(),
        )
        # monkeypatch discover inside run_once path
        orig = sch.discover_and_ingest
        sch.discover_and_ingest = fake_discover
        try:
            r1 = await sched.run_once()
            assert r1["ran"] is True
            r2 = await sched.run_once()
            assert r2["ran"] is False  # min_interval
            sched.state.last_success_at = time.time() - 4000
            r3 = await sched.run_once()
            assert r3["ran"] is True
            r4 = await sched.run_once()
            assert r4["ran"] is False  # daily budget 2
            ui = sched.ui_status()
            assert ui["cycles_today"] == 2
            assert "next_run_in_s" in ui
            assert ui["budget"]["max_cycles_per_day"] == 2
        finally:
            sch.discover_and_ingest = orig

    import asyncio
    asyncio.run(run())
