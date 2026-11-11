"""Local GLiNER service for the main API client (`knowledge/gliner_client.py`).

Replaces the remote process on server 1 for development: same port and contract.

Endpoints:
  GET  /health   — status, model, revision
  POST /extract  — {text, labels, slide, threshold} -> {model, entities}

Run (bind to loopback only; there is no authentication):
  uvicorn gliner_service:app --host 127.0.0.1 --port 8010
Env:
  GLINER_MODEL_ID=urchade/gliner_multi-v2.1
  GLINER_REVISION=443d26d654e0324125a96bebd8e796c14ff2efe6
  GLINER_DEVICE=cpu            # cpu | mps
  GLINER_MAX_CHARS=50000       # longer text -> 413
  GLINER_CHUNK_WORDS=200       # the model sees at most 384 tokens at once
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_ID = os.environ.get("GLINER_MODEL_ID", "urchade/gliner_multi-v2.1")
MODEL_REVISION = os.environ.get("GLINER_REVISION", "443d26d654e0324125a96bebd8e796c14ff2efe6")
DEVICE = os.environ.get("GLINER_DEVICE", "cpu")
MAX_CHARS = int(os.environ.get("GLINER_MAX_CHARS", "50000"))
CHUNK_WORDS = int(os.environ.get("GLINER_CHUNK_WORDS", "200"))
MAX_LABELS = 25

app = FastAPI(title="macromind-gliner", version="0.1")

_state: dict[str, Any] = {"ready": False, "model": None, "error": None}
_lock = threading.Lock()


class ExtractRequest(BaseModel):
    text: str
    labels: list[str] = Field(min_length=1, max_length=MAX_LABELS)
    slide: int | None = None
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)


def load_model() -> None:
    """Загрузка один раз; повторный вызов после ошибки пробует снова."""
    with _lock:
        if _state["ready"]:
            return
        try:
            from gliner import GLiNER

            model = GLiNER.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
            model = model.to(DEVICE)
            model.eval()
            _state["model"] = model
            _state["ready"] = True
            _state["error"] = None
        except Exception as exc:  # noqa: BLE001
            _state["error"] = str(exc)[:300]
            _state["ready"] = False


def split_text(text: str, max_words: int = CHUNK_WORDS) -> list[tuple[int, str]]:
    """Делит текст на куски не длиннее max_words слов с их смещением в исходном тексте.

    Модель молча обрезает длинный вход, поэтому длинный текст подаётся частями.
    Режем по концу строки или предложения во второй половине окна, иначе по границе слова.
    """
    words = list(re.finditer(r"\S+", text))
    chunks: list[tuple[int, str]] = []
    i = 0
    while i < len(words):
        j = min(i + max_words, len(words))
        if j < len(words):
            for k in range(j - 1, i + max_words // 2 - 1, -1):
                tail = text[words[k].end():words[k + 1].start()]
                if "\n" in tail or words[k].group()[-1] in ".!?;":
                    j = k + 1
                    break
        start, end = words[i].start(), words[j - 1].end()
        chunks.append((start, text[start:end]))
        i = j
    return chunks


def extract(text: str, labels: list[str], threshold: float, slide: int | None) -> list[dict[str, Any]]:
    model = _state["model"]
    entities: list[dict[str, Any]] = []
    with _lock:
        for offset, chunk in split_text(text):
            for item in model.predict_entities(chunk, labels, threshold=threshold):
                start, end = offset + int(item["start"]), offset + int(item["end"])
                entities.append({
                    "text": text[start:end],
                    "type": item["label"],
                    "start": start,
                    "end": end,
                    "score": round(float(item["score"]), 4),
                    "slide": slide,
                })
    return entities


@app.on_event("startup")
async def _startup() -> None:
    load_model()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if _state["ready"] else "error",
        "ready": _state["ready"],
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "device": DEVICE,
        "error": _state["error"],
    }


@app.post("/extract")
def extract_endpoint(req: ExtractRequest) -> dict[str, Any]:
    if len(req.text) > MAX_CHARS:
        raise HTTPException(status_code=413, detail="Текст длиннее лимита")
    labels = [label.strip() for label in req.labels if label.strip()]
    if not labels:
        raise HTTPException(status_code=422, detail="Не заданы метки")
    if not _state["ready"]:
        load_model()
        if not _state["ready"]:
            raise HTTPException(status_code=503, detail="Модель не готова")
    entities = extract(req.text, labels, req.threshold, req.slide) if req.text.strip() else []
    return {"model": MODEL_ID.rsplit("/", 1)[-1], "revision": MODEL_REVISION, "entities": entities}
