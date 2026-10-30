"""LLM response cache + cost ledger + limits (spec Task1 §10, F32–F34).

Cache key includes model, prompt version, schema hash, evidence hash — not just INN.
Errors are never cached as success.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_key(
    *,
    model: str,
    prompt_version: str,
    system: str,
    payload: dict[str, Any],
) -> str:
    """F33: ключ зависит от инструкции, схемы и доказательств."""
    blob = json.dumps(
        {
            "model": model,
            "prompt_version": prompt_version,
            "system": system,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class CacheEntry:
    key: str
    text: str
    usage: dict[str, Any]
    created_at: str
    hits: int = 0


class LLMCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict[str, CacheEntry] = {}
        self._inflight: dict[str, threading.Event] = {}

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            e = self._data.get(key)
            if e:
                e.hits += 1
            return e

    def put(self, key: str, text: str, usage: dict[str, Any] | None = None) -> CacheEntry:
        with self._lock:
            e = CacheEntry(key=key, text=text, usage=usage or {}, created_at=_now())
            self._data[key] = e
            return e

    def coalesce(self, key: str) -> threading.Event | None:
        """F32: одновременные одинаковые запросы объединяются."""
        with self._lock:
            if key in self._inflight:
                return self._inflight[key]
            ev = threading.Event()
            self._inflight[key] = ev
            return None

    def release(self, key: str) -> None:
        with self._lock:
            ev = self._inflight.pop(key, None)
        if ev:
            ev.set()

    def wait_inflight(self, key: str, timeout: float = 30.0) -> CacheEntry | None:
        with self._lock:
            ev = self._inflight.get(key)
        if ev:
            ev.wait(timeout)
        return self.get(key)

    async def wait_inflight_async(self, key: str, timeout: float = 30.0) -> CacheEntry | None:
        """Wait without occupying the event loop or a thread per duplicate request."""
        with self._lock:
            event = self._inflight.get(key)
        deadline = time.monotonic() + timeout
        while event is not None and not event.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        return self.get(key)


class CostLedger:
    """Простой журнал расходов; стоимость расчётная, если поставщик не вернул usage."""

    def __init__(self):
        self._lock = threading.Lock()
        self.entries: list[dict[str, Any]] = []

    def record(
        self,
        *,
        provider: str,
        task: str,
        status: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_rub: float | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid4()),
            "provider": provider,
            "task": task,
            "status": status,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_rub": cost_rub,
            "cost_is_estimated": cost_rub is not None,
            "note": note,
            "at": _now(),
        }
        with self._lock:
            self.entries.append(row)
        return row


class BudgetLimit:
    """F34: лимит на число платных вызовов; при исчерпании — без нового вызова."""

    def __init__(self, max_paid_calls: int = 20, max_parallel: int = 2):
        self.max_paid_calls = max_paid_calls
        self.max_parallel = max_parallel
        self.paid_calls = 0
        self._parallel = 0
        self._lock = threading.Lock()
        self.stopped_reason: str | None = None

    def try_acquire(self) -> tuple[bool, str | None]:
        with self._lock:
            if self.paid_calls + self._parallel >= self.max_paid_calls:
                self.stopped_reason = "Достигнут лимит платных вызовов модели"
                return False, self.stopped_reason
            if self._parallel >= self.max_parallel:
                return False, "Слишком много одновременных обращений"
            self._parallel += 1
            return True, None

    def release(self, *, count_as_paid: bool = True) -> None:
        with self._lock:
            self._parallel = max(0, self._parallel - 1)
            if count_as_paid:
                self.paid_calls += 1


# process-wide
_SHARED_CACHE = LLMCache()
_SHARED_LEDGER = CostLedger()
_SHARED_BUDGET = BudgetLimit()


def shared_cache() -> LLMCache:
    return _SHARED_CACHE


def shared_ledger() -> CostLedger:
    return _SHARED_LEDGER


def shared_budget() -> BudgetLimit:
    return _SHARED_BUDGET
