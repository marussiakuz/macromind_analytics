"""CPU embedding service for Qwen3-Embedding-0.6B (Task2 RAG §7).

Endpoints:
  GET  /health/live
  GET  /health/ready   — model, revision, dimension
  POST /internal/embeddings

Run (server 2 / local CPU):
  uvicorn embedding_service:app --host 0.0.0.0 --port 8090
Env:
  EMBED_MODEL_ID=Qwen/Qwen3-Embedding-0.6B
  EMBED_REVISION=main
  EMBED_DIM=1024
  EMBED_MAX_TOKENS=1024
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_ID = os.environ.get("EMBED_MODEL_ID", "Qwen/Qwen3-Embedding-0.6B")
MODEL_REVISION = os.environ.get("EMBED_REVISION", "main")
DIM = int(os.environ.get("EMBED_DIM", "1024"))
MAX_TOKENS = int(os.environ.get("EMBED_MAX_TOKENS", "1024"))
MAX_BATCH = int(os.environ.get("EMBED_MAX_BATCH", "1"))
QUEUE_LIMIT = int(os.environ.get("EMBED_QUEUE_LIMIT", "8"))

app = FastAPI(title="macromind-embedding", version="0.1")

_state: dict[str, Any] = {"ready": False, "model": None, "error": None}
_queue_depth = 0


class EmbedRequest(BaseModel):
    input_type: Literal["query", "document"] = "document"
    texts: list[str] = Field(min_length=1)
    request_id: str | None = None
    normalize: bool = True


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    revision: str
    dimension: int
    input_type: str
    prompt_tokens: int
    elapsed_ms: float
    request_id: str


def load_model() -> None:
    """Загрузка один раз; без GPU."""
    if _state["ready"]:
        return
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            MODEL_ID,
            device="cpu",
            model_kwargs={"torch_dtype": "float32"},
        )
        _state["model"] = model
        _state["ready"] = True
        _state["error"] = None
    except Exception as exc:  # noqa: BLE001
        _state["error"] = str(exc)[:300]
        _state["ready"] = False


@app.on_event("startup")
async def _startup() -> None:
    # ленивая загрузка в фоне не требуется; health/ready отразит состояние
    load_model()


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, Any]:
    return {
        "ready": _state["ready"],
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "dimension": DIM,
        "max_tokens": MAX_TOKENS,
        "error": _state["error"],
    }


@app.post("/internal/embeddings", response_model=EmbedResponse)
async def embeddings(req: EmbedRequest) -> EmbedResponse:
    global _queue_depth
    if not _state["ready"]:
        load_model()
        if not _state["ready"]:
            raise HTTPException(status_code=503, detail="Модель не готова")
    if len(req.texts) > MAX_BATCH * 8:
        raise HTTPException(status_code=422, detail="Слишком много текстов в одном запросе")
    # грубая проверка длины по словам (точный токенизатор — в модели)
    for t in req.texts:
        if len(t.split()) > MAX_TOKENS * 2:
            raise HTTPException(status_code=422, detail="Вход длиннее лимита")

    if _queue_depth >= QUEUE_LIMIT:
        raise HTTPException(status_code=429, detail="Очередь переполнена")
    _queue_depth += 1
    started = time.perf_counter()
    try:
        model = _state["model"]
        prompt_name = "query" if req.input_type == "query" else None
        vectors = model.encode(
            req.texts,
            prompt_name=prompt_name,
            normalize_embeddings=req.normalize,
            batch_size=MAX_BATCH,
        )
        out = [[float(x) for x in v[:DIM]] for v in vectors]
        # оценим токены грубо
        prompt_tokens = sum(max(1, len(t.split())) for t in req.texts)
        return EmbedResponse(
            vectors=out,
            revision=MODEL_REVISION,
            dimension=DIM,
            input_type=req.input_type,
            prompt_tokens=prompt_tokens,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            request_id=req.request_id or str(uuid.uuid4()),
        )
    finally:
        _queue_depth -= 1
