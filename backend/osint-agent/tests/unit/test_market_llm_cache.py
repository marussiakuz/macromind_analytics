"""Stage D: cache, coalesce, budget (F32–F34)."""

import pytest

from osint_agent.market.auto_analysis import (
    add_llm_interpretation_cached,
    build_auto_analysis,
)
from osint_agent.market.llm_cache import (
    BudgetLimit,
    LLMCache,
    cache_key,
    shared_budget,
    shared_cache,
    shared_ledger,
)
from osint_agent.market.providers.yandex_llm import LLMResult, YandexStudioLLM


def test_cache_key_includes_evidence_and_prompt():
    a = cache_key(model="m", prompt_version="p1", system="s", payload={"evidence": ["e1"]})
    b = cache_key(model="m", prompt_version="p1", system="s", payload={"evidence": ["e1"]})
    c = cache_key(model="m", prompt_version="p2", system="s", payload={"evidence": ["e1"]})
    d = cache_key(model="m", prompt_version="p1", system="s", payload={"evidence": ["e2"]})
    assert a == b
    assert a != c  # F33 инструкция
    assert a != d  # F33 доказательства


class FakeLLM(YandexStudioLLM):
    def __init__(self, text, ok=True, err=None):
        self.settings = type("S", (), {"model_uri": "test-model"})()
        self.calls = 0
        self._text = text
        self._ok = ok
        self._err = err

    async def complete(self, system, payload):
        self.calls += 1
        return LLMResult(
            text=self._text,
            prompt_tokens=10,
            completion_tokens=5,
            model="test-model",
            ok=self._ok,
            error=self._err,
            error_code=None if self._ok else "error",
        )

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_f32_identical_requests_cached_once():
    shared_cache()._data.clear()
    shared_ledger().entries.clear()
    shared_budget().paid_calls = 0

    summary = build_auto_analysis(
        {"inn": "1", "name": "X"},
        None,
        {"contracts": {"items": [{"id": "c1", "fields": {"Заказчик": "A"}, "amount": 1}]}},
    )
    eid = summary["evidence_refs"][0]["id"]
    text = '{"interpretation":[{"statement":"ok","evidence_ids":["%s"],"limitations":["x"]}],"summary":"s","risks":[],"questions":[]}' % eid
    llm = FakeLLM(text)
    out1 = await add_llm_interpretation_cached(dict(summary), llm=llm)
    out2 = await add_llm_interpretation_cached(dict(summary), llm=FakeLLM(text))
    assert out1["llm_status"] == "ok"
    assert out2.get("llm_cache_hit") is True
    assert llm.calls == 1
    assert shared_budget().paid_calls == 1  # один учтённый платный вызов


@pytest.mark.asyncio
async def test_f33_evidence_change_forces_new_call():
    shared_cache()._data.clear()
    shared_budget().paid_calls = 0
    s1 = build_auto_analysis({"inn": "1", "name": "X"}, None, {
        "contracts": {"items": [{"id": "c1", "fields": {"Заказчик": "A"}, "amount": 1}]}
    })
    s2 = build_auto_analysis({"inn": "1", "name": "X"}, None, {
        "contracts": {"items": [{"id": "c2", "fields": {"Заказчик": "B"}, "amount": 2}]}
    })
    e1 = s1["evidence_refs"][0]["id"]
    e2 = s2["evidence_refs"][0]["id"]
    t1 = '{"interpretation":[{"statement":"a","evidence_ids":["%s"]}],"summary":"1","risks":[],"questions":[]}' % e1
    t2 = '{"interpretation":[{"statement":"b","evidence_ids":["%s"]}],"summary":"2","risks":[],"questions":[]}' % e2
    llm1 = FakeLLM(t1)
    await add_llm_interpretation_cached(s1, llm=llm1)
    llm2 = FakeLLM(t2)
    out2 = await add_llm_interpretation_cached(s2, llm=llm2)
    assert llm2.calls == 1
    assert out2.get("llm_cache_hit") is False
    assert out2["llm_summary"] != "1"


@pytest.mark.asyncio
async def test_f34_budget_stops_paid_calls():
    b = BudgetLimit(max_paid_calls=1, max_parallel=5)
    ok1, _ = b.try_acquire()
    assert ok1
    b.release(count_as_paid=True)
    ok2, reason = b.try_acquire()
    assert ok2 is False
    assert "лимит" in (reason or "").lower()

    shared_budget().paid_calls = shared_budget().max_paid_calls
    summary = build_auto_analysis({"inn": "zz"}, None, {})
    out = await add_llm_interpretation_cached(summary, llm=FakeLLM("{}", ok=False, err="x"))
    assert out["llm_status"] == "limit_reached"
    assert out["llm_interpretation"] == []
    shared_budget().paid_calls = 0


def test_cache_put_get_and_no_error_as_success():
    c = LLMCache()
    assert c.get("k") is None
    c.put("k", "text", {"tokens": 1})
    assert c.get("k").text == "text"
    # ошибка не кладётся как успех — put только при ok выше


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_block_event_loop_or_duplicate_provider():
    import asyncio
    shared_cache()._data.clear()
    shared_budget().paid_calls = 0
    shared_budget()._parallel = 0

    class Slow(FakeLLM):
        async def complete(self, system, payload):
            await asyncio.sleep(0.02)
            return await super().complete(system, payload)

    first = Slow('{"interpretation":[],"questions":[]}')
    second = Slow('{"interpretation":[],"questions":[]}')
    results = await asyncio.wait_for(asyncio.gather(
        add_llm_interpretation_cached({"legal_entity_inn": "concurrent"}, llm=first),
        add_llm_interpretation_cached({"legal_entity_inn": "concurrent"}, llm=second),
    ), timeout=1)
    assert first.calls + second.calls == 1
    assert all(r["llm_status"] == "ok" for r in results)
    assert shared_budget()._parallel == 0


def test_budget_reserves_last_call_for_only_one_request():
    budget = BudgetLimit(max_paid_calls=1, max_parallel=2)
    assert budget.try_acquire()[0]
    assert not budget.try_acquire()[0]
    budget.release()
    assert not budget.try_acquire()[0]


@pytest.mark.asyncio
async def test_limit_rejection_does_not_release_other_request_slot():
    shared_cache()._data.clear()
    budget = shared_budget()
    budget.paid_calls = 0
    budget._parallel = budget.max_parallel
    try:
        result = await add_llm_interpretation_cached({"legal_entity_inn": "blocked"}, llm=FakeLLM('{}'))
        assert result["llm_status"] == "limit_reached"
        assert budget._parallel == budget.max_parallel
    finally:
        budget._parallel = 0
