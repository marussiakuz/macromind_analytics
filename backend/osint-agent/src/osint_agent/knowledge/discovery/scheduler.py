"""Discovery scheduler with interval + budget (MIMO_DISCOVERY §5).

Run as a long-lived process on server 1, or invoke run_once from cron.
Budget caps Yandex/OpenAlex fetches and external downloads per cycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from osint_agent.knowledge.discovery.pipeline import DiscoveryResult, discover_and_ingest
from osint_agent.knowledge.discovery.queries import ProductProfile

log = logging.getLogger(__name__)


@dataclass
class DiscoveryBudget:
    max_yandex_hits_per_cycle: int = 20
    max_openalex_per_cycle: int = 25
    max_fetches_per_cycle: int = 15
    max_cycles_per_day: int = 24
    min_interval_seconds: float = 3600.0


@dataclass
class SchedulerState:
    last_success_at: float | None = None
    last_error: str | None = None
    cycles_today: int = 0
    day_key: str = ""
    total_ingested: int = 0
    total_failed: int = 0
    history: list[dict] = field(default_factory=list)


class DiscoveryScheduler:
    def __init__(
        self,
        *,
        profiles: list[ProductProfile],
        repo_factory: Callable[[], Any],
        workspace_id: str,
        budget: DiscoveryBudget | None = None,
        state: SchedulerState | None = None,
    ):
        self.profiles = profiles
        self.repo_factory = repo_factory
        self.workspace_id = workspace_id
        self.budget = budget or DiscoveryBudget()
        self.state = state or SchedulerState()

    def _roll_day(self) -> None:
        day = time.strftime("%Y-%m-%d")
        if self.state.day_key != day:
            self.state.day_key = day
            self.state.cycles_today = 0

    def should_run(self) -> tuple[bool, str]:
        self._roll_day()
        if self.state.cycles_today >= self.budget.max_cycles_per_day:
            return False, "daily_cycle_budget_exhausted"
        if self.state.last_success_at is not None:
            elapsed = time.time() - self.state.last_success_at
            if elapsed < self.budget.min_interval_seconds:
                return False, f"min_interval_not_elapsed:{int(elapsed)}"
        return True, "ok"

    async def run_once(self) -> dict[str, Any]:
        ok, reason = self.should_run()
        if not ok:
            return {"ran": False, "reason": reason, "state": self._state_dict()}

        results: list[dict[str, Any]] = []
        repo = self.repo_factory()
        try:
            for profile in self.profiles:
                try:
                    r: DiscoveryResult = await discover_and_ingest(
                        profile,
                        repo,
                        workspace_id=self.workspace_id,
                        max_yandex_docs=min(12, self.budget.max_fetches_per_cycle),
                        max_openalex=self.budget.max_openalex_per_cycle,
                    )
                    self.state.total_ingested += r.ingested
                    self.state.total_failed += r.failed
                    results.append({
                        "product": profile.product,
                        "ingested": r.ingested,
                        "failed": r.failed,
                        "yandex_hits": len(r.yandex_hits),
                        "openalex_works": len(r.openalex_works),
                        "limitations": r.limitations,
                    })
                except Exception as exc:  # noqa: BLE001
                    self.state.last_error = f"{type(exc).__name__}: {exc}"[:200]
                    results.append({"product": profile.product, "error": self.state.last_error})
        finally:
            close = getattr(repo, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass

        self.state.cycles_today += 1
        self.state.last_success_at = time.time()
        self.state.history.append({
            "at": self.state.last_success_at,
            "results": results,
        })
        self.state.history = self.state.history[-50:]
        return {"ran": True, "reason": "ok", "results": results, "state": self._state_dict()}

    def _state_dict(self) -> dict[str, Any]:
        return {
            "last_success_at": self.state.last_success_at,
            "last_error": self.state.last_error,
            "cycles_today": self.state.cycles_today,
            "day_key": self.state.day_key,
            "total_ingested": self.state.total_ingested,
            "total_failed": self.state.total_failed,
        }

    def ui_status(self) -> dict[str, Any]:
        """§5: last success, document counts, delays, error reasons."""
        now = time.time()
        delay_s = (
            max(0.0, self.budget.min_interval_seconds - (now - self.state.last_success_at))
            if self.state.last_success_at else 0.0
        )
        return {
            "last_success_at": self.state.last_success_at,
            "last_error": self.state.last_error,
            "documents_ingested_total": self.state.total_ingested,
            "failed_total": self.state.total_failed,
            "cycles_today": self.state.cycles_today,
            "next_run_in_s": delay_s,
            "budget": {
                "max_cycles_per_day": self.budget.max_cycles_per_day,
                "min_interval_seconds": self.budget.min_interval_seconds,
                "max_fetches_per_cycle": self.budget.max_fetches_per_cycle,
            },
        }

    async def serve(self, *, once: bool = False, interval_s: float | None = None) -> None:
        interval = interval_s or self.budget.min_interval_seconds
        while True:
            out = await self.run_once()
            log.info("discovery cycle %s", out.get("reason"))
            if once:
                return
            await asyncio.sleep(max(60.0, interval))


def scheduler_from_env(profiles: list[ProductProfile], *, workspace_id: str) -> DiscoveryScheduler:
    from osint_agent.knowledge.env import apply_knowledge_env, knowledge_dsn
    from osint_agent.knowledge.pg_repository import KnowledgePgRepository

    apply_knowledge_env()

    def factory():
        dsn = knowledge_dsn()
        if not dsn:
            raise RuntimeError("KNOWLEDGE_DATABASE_URL is not set")
        return KnowledgePgRepository(dsn)

    budget = DiscoveryBudget(
        max_yandex_hits_per_cycle=int(os.environ.get("DISCOVERY_MAX_YANDEX", "20")),
        max_openalex_per_cycle=int(os.environ.get("DISCOVERY_MAX_OPENALEX", "25")),
        max_fetches_per_cycle=int(os.environ.get("DISCOVERY_MAX_FETCHES", "15")),
        max_cycles_per_day=int(os.environ.get("DISCOVERY_MAX_CYCLES_PER_DAY", "24")),
        min_interval_seconds=float(os.environ.get("DISCOVERY_INTERVAL_S", "3600")),
    )
    return DiscoveryScheduler(
        profiles=profiles, repo_factory=factory, workspace_id=workspace_id, budget=budget
    )
