"""Measure retrieval quality vs final answer quality separately (§6.5 p.9).

Retrieval metrics: latency, recall@k, empty rate, limitations.
Answer metrics: latency, citations present, false claims, cost estimate.
Never treat retrieval success as answer correctness.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RetrievalMetric:
    question: str
    latency_ms: float
    n_items: int
    empty_reason: str | None
    limitations: list[str] = field(default_factory=list)
    hit: bool | None = None  # gold vs returned (None if unlabeled)


@dataclass
class AnswerMetric:
    question: str
    latency_ms: float
    n_items_used: int
    has_citation: bool
    false_claim_suspected: bool
    cost_rub: float | None
    answer_chars: int
    notes: str = ""


@dataclass
class DualEvalResult:
    retrieval: list[RetrievalMetric]
    answers: list[AnswerMetric]

    def summary(self) -> dict[str, Any]:
        ret = self.retrieval
        ans = self.answers
        ret_lat = [r.latency_ms for r in ret]
        ans_lat = [a.latency_ms for a in ans]
        return {
            "n_questions": len(ret),
            "retrieval": {
                "avg_latency_ms": sum(ret_lat) / len(ret_lat) if ret_lat else None,
                "p95_latency_ms": sorted(ret_lat)[int(len(ret_lat) * 0.95) - 1] if ret_lat else None,
                "empty_rate": sum(1 for r in ret if r.n_items == 0) / len(ret) if ret else None,
                "hit_rate": (
                    sum(1 for r in ret if r.hit) / sum(1 for r in ret if r.hit is not None)
                    if any(r.hit is not None for r in ret) else None
                ),
            },
            "answer": {
                "avg_latency_ms": sum(ans_lat) / len(ans_lat) if ans_lat else None,
                "citation_rate": (
                    sum(1 for a in ans if a.has_citation) / len(ans) if ans else None
                ),
                "false_claim_rate": (
                    sum(1 for a in ans if a.false_claim_suspected) / len(ans) if ans else None
                ),
                "avg_cost_rub": (
                    sum(a.cost_rub for a in ans if a.cost_rub is not None)
                    / max(1, sum(1 for a in ans if a.cost_rub is not None))
                ) if any(a.cost_rub is not None for a in ans) else None,
            },
        }


def _has_citation(text: str, evidence_ids: list[str]) -> bool:
    if not text:
        return False
    if re.search(r"\[[^\]]{2,40}\]|\(источник|source:|doi:|http", text, re.I):
        return True
    return any(eid and eid[:8] in text for eid in evidence_ids or [])


def _false_claim_suspected(text: str, forbidden: list[str] | None) -> bool:
    low = (text or "").lower()
    for bad in forbidden or []:
        if bad and bad.lower() in low:
            return True
    return False


def evaluate_retrieval_vs_answer(
    questions: list[dict],
    *,
    retrieve_fn: Callable[[dict], Any],
    answer_fn: Callable[[dict, Any], str] | None = None,
) -> DualEvalResult:
    """Run retrieval and (optional) answer generation with separate timings.

    questions: [{id, question, answerable, relevant_ids/titles, forbidden_claims}]
    retrieve_fn(q) -> object with .items and optional .empty_reason/.limitations
    answer_fn(q, retrieval) -> str final answer text
    """
    ret_metrics: list[RetrievalMetric] = []
    ans_metrics: list[AnswerMetric] = []

    for q in questions:
        t0 = time.perf_counter()
        res = retrieve_fn(q)
        ret_ms = (time.perf_counter() - t0) * 1000
        items = list(getattr(res, "items", None) or [])
        hit = None
        gold = set(q.get("relevant_ids") or q.get("relevant_document_ids") or [])
        titles = [str(g).lower() for g in (q.get("relevant_titles") or [])]
        if q.get("answerable", True) and (gold or titles):
            blob = " ".join((getattr(i, "title", "") or "") + (getattr(i, "excerpt", "") or "") for i in items)
            if gold:
                got = {str(getattr(i, "document_id", "") or "") for i in items}
                hit = bool(got & gold)
            if hit is None and titles:
                hit = any(t in blob.lower() for t in titles)
            if not items:
                hit = False  # empty positive = miss (§6.5 p.7)
        ret_metrics.append(RetrievalMetric(
            question=q.get("question") or q.get("id") or "",
            latency_ms=ret_ms,
            n_items=len(items),
            empty_reason=getattr(res, "empty_reason", None),
            limitations=list(getattr(res, "limitations", None) or []),
            hit=hit,
        ))

        if answer_fn is None:
            continue
        t1 = time.perf_counter()
        try:
            answer = answer_fn(q, res) or ""
        except Exception as exc:  # noqa: BLE001
            answer = ""
            note = type(exc).__name__
        else:
            note = ""
        ans_ms = (time.perf_counter() - t1) * 1000
        eids = [str(getattr(i, "evidence_id", "") or getattr(i, "document_id", "") or "") for i in items]
        ans_metrics.append(AnswerMetric(
            question=q.get("question") or q.get("id") or "",
            latency_ms=ans_ms,
            n_items_used=len(items),
            has_citation=_has_citation(answer, eids),
            false_claim_suspected=_false_claim_suspected(
                answer, q.get("forbidden_claims") or q.get("forbidden")
            ),
            cost_rub=q.get("estimated_cost_rub"),
            answer_chars=len(answer),
            notes=note,
        ))

    return DualEvalResult(retrieval=ret_metrics, answers=ans_metrics)
