"""Local GLiNER service: chunking, offsets and the contract of `GlinerClient`."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICE = Path(__file__).resolve().parents[2] / "services" / "gliner" / "gliner_service.py"


@pytest.fixture()
def service(monkeypatch):
    spec = importlib.util.spec_from_file_location("gliner_service_under_test", SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module


class FakeModel:
    """Находит каждое вхождение слова «Сбер» как компанию."""

    def __init__(self):
        self.calls = []

    def predict_entities(self, text, labels, threshold=0.5):
        self.calls.append((text, tuple(labels), threshold))
        out = []
        start = text.find("Сбер")
        while start != -1:
            out.append({"start": start, "end": start + 4, "text": "Сбер", "label": labels[0], "score": 0.91234})
            start = text.find("Сбер", start + 1)
        return out


def test_split_text_keeps_offsets_and_limits_words(service):
    text = " ".join(f"w{i}" for i in range(450))
    chunks = service.split_text(text, max_words=200)
    assert [len(c.split()) for _, c in chunks] == [200, 200, 50]
    for offset, chunk in chunks:
        assert text[offset:offset + len(chunk)] == chunk


def test_split_text_prefers_sentence_end(service):
    text = ("a " * 150).strip() + ". " + ("b " * 100).strip()
    chunks = service.split_text(text, max_words=200)
    assert chunks[0][1].endswith("a.")
    assert chunks[1][1].startswith("b")


def test_extract_maps_chunk_offsets_back_to_text(service):
    model = FakeModel()
    service._state.update(ready=True, model=model)
    text = ("слово " * 250) + "Сбер инвестировал"
    client = TestClient(service.app)
    r = client.post("/extract", json={"text": text, "labels": ["компания"], "slide": 4, "threshold": 0.4})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "gliner_multi-v2.1"
    [entity] = body["entities"]
    assert text[entity["start"]:entity["end"]] == "Сбер" == entity["text"]
    assert entity["type"] == "компания" and entity["slide"] == 4 and entity["score"] == 0.9123
    assert len(model.calls) == 2 and model.calls[0][2] == 0.4


def test_extract_rejects_long_text_and_empty_labels(service):
    service._state.update(ready=True, model=FakeModel())
    client = TestClient(service.app)
    assert client.post("/extract", json={"text": "x" * (service.MAX_CHARS + 1), "labels": ["a"]}).status_code == 413
    assert client.post("/extract", json={"text": "Сбер", "labels": [" "]}).status_code == 422
    assert client.post("/extract", json={"text": "Сбер", "labels": []}).status_code == 422


def test_extract_returns_503_when_model_missing(service, monkeypatch):
    monkeypatch.setattr(service, "load_model", lambda: None)
    service._state.update(ready=False, model=None, error="no weights")
    client = TestClient(service.app)
    assert client.post("/extract", json={"text": "Сбер", "labels": ["компания"]}).status_code == 503
    health = client.get("/health").json()
    assert health["ready"] is False and health["error"] == "no weights"
