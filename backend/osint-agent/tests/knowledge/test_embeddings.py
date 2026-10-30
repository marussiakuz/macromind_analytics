"""Embedding client tests (Task2 Stage C)."""

import httpx
import pytest

from osint_agent.knowledge.embeddings import DIM, EmbeddingClient


def _vec():
    return [0.01] * DIM


@pytest.mark.asyncio
async def test_embed_ok_query_mode():
    def handler(request):
        import json

        body = json.loads(request.content)
        assert body["input_type"] == "query"
        return httpx.Response(200, json={
            "vectors": [_vec()],
            "revision": "r1",
            "dimension": DIM,
            "input_type": "query",
            "prompt_tokens": 5,
            "elapsed_ms": 12.5,
        })

    c = EmbeddingClient("http://test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        res = await c.embed(["вопрос"], input_type="query")
    finally:
        await c.aclose()
    assert res.ok
    assert res.dimension == DIM
    assert len(res.vectors[0]) == DIM


@pytest.mark.asyncio
async def test_embed_errors_mapped():
    for status, code in ((422, "invalid_input"), (429, "rate_limited"), (503, "not_ready")):

        def handler(request, status=status):
            return httpx.Response(status)

        c = EmbeddingClient("http://t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            res = await c.embed(["x"])
        finally:
            await c.aclose()
        assert res.ok is False
        assert res.error_code == code


@pytest.mark.asyncio
async def test_embed_empty_and_unavailable():
    c = EmbeddingClient("http://t", client=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"vectors": [], "dimension": DIM})
    )))
    try:
        empty = await c.embed([])
        assert empty.error_code == "empty"
        bad = await c.embed(["x"])
        assert bad.error_code == "bad_response"
    finally:
        await c.aclose()


def test_query_vector_unwraps_single_embedding():
    from osint_agent.knowledge.embeddings import query_vector

    flat = query_vector({"vectors": [[0.1, 0.2, 0.3]]})
    assert flat == [0.1, 0.2, 0.3]
    assert query_vector({"vectors": []}) == []
    assert query_vector({}) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"vectors": [[0.1]*1023], "dimension": DIM, "revision": "r"},
    {"vectors": [[0.1]*1024]*2, "dimension": DIM, "revision": "r"},
    {"vectors": [[0.0]*1024], "dimension": DIM, "revision": "r"},
    {"vectors": [[True]*1024], "dimension": DIM, "revision": "r"},
    {"vectors": [[0.1]*1024], "dimension": 2, "revision": "r"},
    {"vectors": [[0.1]*1024], "dimension": DIM},
    [],
])
async def test_malformed_vector_response_is_not_success(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as http:
        result = await EmbeddingClient("http://test", client=http).embed(["text"])
    assert not result.ok
    assert result.error_code == "bad_response"
