"""Shared research budget for one company check (Astra P2 / plan §6)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResearchBudget:
    """One residual budget for searches, document reads, time, model calls."""

    max_search_queries: int = 24
    max_document_reads: int = 40
    max_model_calls: int = 8
    max_backup_search: int = 2
    max_seconds: float = 900.0
    started_at: float = field(default_factory=time.monotonic)
    used_search: int = 0
    used_reads: int = 0
    used_model: int = 0
    used_backup_search: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_seconds - (time.monotonic() - self.started_at))

    def can_search(self, n: int = 1) -> bool:
        return self.used_search + n <= self.max_search_queries and self.remaining_seconds() > 15

    def can_read(self, n: int = 1) -> bool:
        return self.used_reads + n <= self.max_document_reads and self.remaining_seconds() > 10

    def can_call_model(self, n: int = 1) -> bool:
        return self.used_model + n <= self.max_model_calls and self.remaining_seconds() > 20

    def consume_search(self, n: int = 1, *, label: str = "") -> int:
        """Returns how many are actually allowed and records usage."""
        allowed = max(0, min(n, self.max_search_queries - self.used_search)) if self.remaining_seconds() > 15 else 0
        self.used_search += allowed
        self.log.append({"kind": "search", "n": allowed, "label": label,
                         "remaining_queries": self.max_search_queries - self.used_search})
        return allowed

    def consume_reads(self, n: int = 1, *, label: str = "") -> int:
        allowed = max(0, min(n, self.max_document_reads - self.used_reads)) if self.remaining_seconds() > 10 else 0
        self.used_reads += allowed
        self.log.append({"kind": "read", "n": allowed, "label": label,
                         "remaining_reads": self.max_document_reads - self.used_reads})
        return allowed

    def consume_model(self, n: int = 1, *, label: str = "") -> int:
        allowed = max(0, min(n, self.max_model_calls - self.used_model))
        self.used_model += allowed
        self.log.append({"kind": "model", "n": allowed, "label": label,
                         "remaining_model": self.max_model_calls - self.used_model})
        return allowed

    def consume_backup_search(self, n: int = 1, *, label: str = "") -> int:
        """Запасной поиск: ограниченный остаточный бюджет внутри общего бюджета."""
        allowed = max(0, min(n, self.max_backup_search - self.used_backup_search,
                             self.max_search_queries - self.used_search)) if self.remaining_seconds() > 15 else 0
        self.used_backup_search += allowed
        self.used_search += allowed
        self.log.append({"kind": "backup_search", "n": allowed, "label": label,
                         "remaining_backup": self.max_backup_search - self.used_backup_search,
                         "remaining_queries": self.max_search_queries - self.used_search})
        return allowed

    def snapshot(self) -> dict[str, Any]:
        return {
            "max_search_queries": self.max_search_queries,
            "used_search": self.used_search,
            "max_backup_search": self.max_backup_search,
            "used_backup_search": self.used_backup_search,
            "max_document_reads": self.max_document_reads,
            "used_reads": self.used_reads,
            "max_model_calls": self.max_model_calls,
            "used_model": self.used_model,
            "elapsed_s": round(time.monotonic() - self.started_at, 2),
            "remaining_s": round(self.remaining_seconds(), 2),
        }
