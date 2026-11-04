"""GLiNER client tests (MIMO_MARKET_RECOVERY §7)."""

import httpx
import pytest

from osint_agent.knowledge.gliner_client import GlinerClient


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_extract_success_normalizes_fields():
    captured = {}

    def handler(request):
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "gliner_multi-v2.1",
            "entities": [
                {"text": "ООО ТОТА СИСТЕМС", "type": "компания", "start": 0, "end": 16,
                 "score": 0.96, "slide": 3},
                {"text": "системы мониторинга", "type": "продукт", "start": 28, "end": 47,
                 "score": 0.83},
            ],
        })

    c = GlinerClient(base_url="http://gliner.test", client=_client(handler))
    try:
        res = await c.extract_entities("ООО ТОТА СИСТЕМС поставляет системы мониторинга",
                                       labels=["компания", "продукт"], slide=3, threshold=0.4)
    finally:
        await c.aclose()
    assert res.ok and res.model == "gliner_multi-v2.1"
    assert captured["body"]["slide"] == 3 and captured["body"]["threshold"] == 0.4
    assert captured["body"]["labels"] == ["компания", "продукт"]
    e = res.entities[0]
    assert (e["text"], e["type"], e["start"], e["end"], e["score"], e["slide"]) == (
        "ООО ТОТА СИСТЕМС", "компания", 0, 16, 0.96, 3)
    # слайд пробрасывается по умолчанию, если сервис не вернул поле
    assert res.entities[1]["slide"] == 3


@pytest.mark.asyncio
async def test_empty_text_and_missing_labels():
    c = GlinerClient(base_url="http://gliner.test", client=_client(lambda r: httpx.Response(200, json={})))
    res = await c.extract_entities("   ")
    assert res.ok and res.entities == []
    res = await c.extract_entities("текст", labels=[])
    assert not res.ok and res.error_code == "bad_request"
    await c.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(413, "too_large"), (500, "unavailable"), (400, "error")])
async def test_http_error_states(status, code):
    c = GlinerClient(base_url="http://gliner.test", client=_client(lambda r: httpx.Response(status, json={})))
    res = await c.extract_entities("текст")
    assert not res.ok and res.error_code == code
    await c.aclose()


@pytest.mark.asyncio
async def test_bad_response_shapes():
    for payload in ({"entities": "oops"}, {"no": "entities"}):
        c = GlinerClient(base_url="http://gliner.test",
                         client=_client(lambda r: httpx.Response(200, json=payload)))
        res = await c.extract_entities("текст")
        assert not res.ok and res.error_code == "bad_response"
        await c.aclose()

    def bad(request):
        return httpx.Response(200, content=b"not-json")

    c = GlinerClient(base_url="http://gliner.test", client=_client(bad))
    res = await c.extract_entities("текст")
    assert not res.ok and res.error_code == "bad_response"
    await c.aclose()


@pytest.mark.asyncio
async def test_timeout_is_error():
    def handler(request):
        raise httpx.ReadTimeout("t")

    c = GlinerClient(base_url="http://gliner.test", client=_client(handler))
    res = await c.extract_entities("текст")
    assert not res.ok and res.error_code == "timeout"
    await c.aclose()


@pytest.mark.asyncio
async def test_health_and_client_ownership():
    c = GlinerClient(base_url="http://gliner.test",
                     client=_client(lambda r: httpx.Response(200, json={"status": "ok"})))
    assert (await c.health())["status"] == "ok"
    await c.aclose()
    owned = GlinerClient(base_url="http://gliner.test")
    oc = await owned._get_client()
    await owned.aclose()
    assert oc.is_closed
