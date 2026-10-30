"""Weak signals: events, hypotheses, watchlists (Task2 RAG §11).

Rules:
- event_at ≠ published_at ≠ detected_at
- reprints share one reprint_cluster_id; independent_sources counts primary sources
- hypothesis holds limitations/alternatives/questions — not a confirmed fact
- zero baseline → no infinite growth (coverage_limited / limitation)
- comparison window marked limited when coverage/queries/limits changed
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from osint_agent.knowledge.pg_repository import KnowledgePgRepository

WINDOW_DAYS = 30
BASELINE_DAYS = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def event_fingerprint(*parts: str | None) -> str:
    """Same underlying event across reprints (§11 p.5)."""
    raw = "|".join(_norm(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class SignalEventInput:
    event_type: str
    subject: str
    technology: str | None = None
    company: str | None = None
    geography: str | None = None
    event_at: date | None = None
    published_at: date | None = None
    source_document_id: str | None = None
    source_evidence_id: str | None = None
    notes: str | None = None
    workspace_id: str | None = None
    watchlist_id: str | None = None


@dataclass
class HypothesisInput:
    statement: str
    event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None
    workspace_id: str | None = None
    watchlist_id: str | None = None
    status: str = "unverified"


class WeakSignalService:
    def __init__(self, repo: KnowledgePgRepository):
        self.repo = repo

    # --- watchlists --------------------------------------------------------

    def save_watchlist(
        self,
        topic: str,
        *,
        products: list[str] | None = None,
        technologies: list[str] | None = None,
        companies: list[str] | None = None,
        queries: list[str] | None = None,
        geography: list[str] | None = None,
        budget: dict | None = None,
        schedule_cron: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        return self.repo.insert_watchlist(
            topic=topic,
            products=products or [],
            technologies=technologies or [],
            companies=companies or [],
            queries=queries or [],
            geography=geography or [],
            budget=budget or {},
            schedule_cron=schedule_cron,
            workspace_id=workspace_id,
        )

    # --- events ------------------------------------------------------------

    def record_event(self, ev: SignalEventInput) -> dict[str, Any]:
        """Upsert by reprint fingerprint; bump independent source counter."""
        cluster = event_fingerprint(
            ev.event_type, ev.subject, ev.technology, str(ev.event_at or "")
        )
        row = self.repo.upsert_signal_event(
            event_type=ev.event_type,
            subject=ev.subject,
            technology=ev.technology,
            company=ev.company,
            geography=ev.geography,
            event_at=ev.event_at,
            published_at=ev.published_at,
            source_document_id=ev.source_document_id,
            source_evidence_id=ev.source_evidence_id,
            reprint_cluster_id=cluster,
            notes=ev.notes,
            workspace_id=ev.workspace_id,
            watchlist_id=ev.watchlist_id,
        )
        return row

    def record_reprint(self, ev: SignalEventInput, *, primary_event_id: str | None = None) -> dict[str, Any]:
        """Reprint does not increase independence (R15)."""
        cluster = event_fingerprint(
            ev.event_type, ev.subject, ev.technology, str(ev.event_at or "")
        )
        if primary_event_id:
            self.repo.link_reprint(primary_event_id, ev.source_document_id, cluster)
            return {"cluster_id": cluster, "primary_event_id": primary_event_id, "counted_independent": False}
        row = self.repo.upsert_signal_event(
            event_type=ev.event_type,
            subject=ev.subject,
            technology=ev.technology,
            company=ev.company,
            geography=ev.geography,
            event_at=ev.event_at,
            published_at=ev.published_at,
            source_document_id=ev.source_document_id,
            source_evidence_id=ev.source_evidence_id,
            reprint_cluster_id=cluster,
            notes=ev.notes,
            workspace_id=ev.workspace_id,
            watchlist_id=ev.watchlist_id,
            increment_independent=False,
        )
        return {"cluster_id": cluster, "primary_event_id": row["id"], "counted_independent": False}

    def list_events(
        self,
        *,
        workspace_id: str | None = None,
        since: date | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self.repo.list_signal_events(workspace_id=workspace_id, since=since, limit=limit)

    # --- hypotheses --------------------------------------------------------

    def form_hypothesis(self, inp: HypothesisInput) -> dict[str, Any]:
        """Build hypothesis with explicit windows and safe baseline math (R31/R32)."""
        limitations = list(inp.limitations)
        window_start = inp.window_start or date.fromordinal(date.today().toordinal() - WINDOW_DAYS)
        window_end = inp.window_end or date.today()
        baseline_start = inp.baseline_start or date.fromordinal(window_start.toordinal() - BASELINE_DAYS)
        baseline_end = inp.baseline_end or window_start

        events_in_window = self.repo.count_signal_events(
            workspace_id=inp.workspace_id, start=window_start, end=window_end
        )
        events_in_baseline = self.repo.count_signal_events(
            workspace_id=inp.workspace_id, start=baseline_start, end=baseline_end
        )
        baseline_days = max(1, (baseline_end - baseline_start).days)
        window_days = max(1, (window_end - window_start).days)

        # normalize by duration; never divide by zero baseline (R31)
        if events_in_baseline == 0:
            limitations.append(
                "Базовое количество событий равно нулю; рост в процентах не рассчитывается"
            )
            rate_note = f"в окне {events_in_window}, в базе 0 — % не считаются"
            status = inp.status if inp.status != "unverified" else "needs_more_data"
        else:
            base_rate = events_in_baseline / baseline_days
            win_rate = events_in_window / window_days
            ratio = win_rate / base_rate if base_rate else None
            rate_note = f"норм. частота окно/база = {ratio:.2f}" if ratio else "n/a"
            status = inp.status

        row = self.repo.insert_signal_hypothesis(
            statement=inp.statement,
            status=status,
            evidence_ids=inp.evidence_ids,
            event_ids=inp.event_ids,
            window_start=window_start,
            window_end=window_end,
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            limitations=limitations,
            alternatives=inp.alternatives,
            questions=inp.questions,
            coverage_limited=bool(limitations),
            workspace_id=inp.workspace_id,
            watchlist_id=inp.watchlist_id,
            extra_notes=rate_note,
        )
        return row

    def list_hypotheses(self, *, workspace_id: str | None = None) -> list[dict]:
        return self.repo.list_signal_hypotheses(workspace_id=workspace_id)
