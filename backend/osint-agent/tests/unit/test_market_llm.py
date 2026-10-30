"""Qwen / Yandex Studio LLM client tests (review §4 acceptance)."""

import json

import httpx
import pytest

from osint_agent.market.auto_analysis import add_llm_interpretation, build_auto_analysis
from osint_agent.market.providers.yandex_llm import (
    INTERPRETATION_SYSTEM,
    LLMSettings,
    YandexStudioLLM,
    parse_interpretation,
)


def _settings():
    return LLMSettings(api_key="test-key", folder_id="folder-1")


def test_model_uri_from_folder():
    s = _settings()
    assert s.model_uri == "gpt://folder-1/qwen3.6-35b-a3b"
    assert s.headers == {"Authorization": "Api-Key test-key"}


@pytest.mark.asyncio
async def test_request_format_matches_radar_client():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"interpretation":[],"summary":"ok"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    llm = YandexStudioLLM(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        res = await llm.complete("system", {"k": "v"})
    finally:
        await llm.aclose()
    assert res.ok and res.model.endswith("qwen3.6-35b-a3b")
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["auth"] == "Api-Key test-key"
    body = captured["body"]
    assert body["model"] == "gpt://folder-1/qwen3.6-35b-a3b"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"
    assert body["reasoning_effort"] == "none"
    assert res.prompt_tokens == 10


@pytest.mark.asyncio
async def test_auth_error_rate_limit_timeout():
    for status, code in ((403, "auth_error"), (429, "rate_limited"), (500, "unavailable")):

        def handler(request, status=status):
            return httpx.Response(status)

        llm = YandexStudioLLM(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            res = await llm.complete("s", {})
        finally:
            await llm.aclose()
        assert res.ok is False
        assert res.error_code == code

    llm = YandexStudioLLM(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
    )))
    # timeout simulated by request error
    async def boom(request):
        raise httpx.TimeoutException("slow")

    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    try:
        res = await llm.complete("s", {})
    finally:
        await llm.aclose()
    assert res.error_code == "timeout"


@pytest.mark.asyncio
async def test_not_configured_keeps_facts():
    llm = YandexStudioLLM(LLMSettings(api_key="", folder_id=""))
    res = await llm.complete("s", {})
    assert res.ok is False
    assert res.error_code == "not_configured"

    summary = build_auto_analysis({"inn": "1", "name": "X"}, None, {"contracts": {"items": []}})
    out = await add_llm_interpretation(summary, llm=YandexStudioLLM(LLMSettings(api_key="", folder_id="")))
    assert out["competitor_findings"] is not None
    assert out["llm_status"] == "not_configured"
    assert out["llm_interpretation"] == []


@pytest.mark.asyncio
async def test_interpretation_claims_normalized():
    payload = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "interpretation": [{
                        "statement": "Рынок фрагментирован",
                        "claim_type": "interpretation",
                        "evidence_ids": ["evidence-0"],
                        "limitations": ["по выборке закупок"],
                    }],
                    "summary": "кратко",
                    "risks": ["риск"],
                    "questions": ["вопрос"],
                }, ensure_ascii=False)
            }
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }

    def handler(request):
        return httpx.Response(200, json=payload)

    llm = YandexStudioLLM(_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    summary = build_auto_analysis({"inn": "1", "name": "X"}, None, {
        "contracts": {"items": [{"id": "c1", "fields": {"Заказчик": "Y"}, "amount": 1}]}
    })
    # id доказательства из summary
    eid = summary["evidence_refs"][0]["id"]
    payload["choices"][0]["message"]["content"] = json.dumps({
        "interpretation": [{
            "statement": "Рынок фрагментирован",
            "claim_type": "interpretation",
            "evidence_ids": [eid],
            "limitations": ["по выборке закупок"],
        }],
        "summary": "кратко",
        "risks": ["риск"],
        "questions": ["вопрос"],
    }, ensure_ascii=False)
    try:
        out = await add_llm_interpretation(summary, llm=llm)
    finally:
        await llm.aclose()
    assert out["llm_status"] == "ok"
    c = out["llm_interpretation"][0]
    assert c["claim_type"] == "interpretation"
    assert c["verification_status"] == "needs_review"
    assert c["limitations"]
    assert c["evidence_ids"] == [eid]
    assert out["llm_model"].endswith("qwen3.6-35b-a3b")


def test_parse_interpretation_fences():
    raw = '```json\n{"summary":"x","interpretation":[]}\n```'
    assert parse_interpretation(raw)["summary"] == "x"
