"""Hybrid retrieval tests (Task2 Stage D, §8)."""

from __future__ import annotations

import math
import os
import uuid

import pytest

from osint_agent.knowledge.pg_repository import KnowledgePgRepository
from osint_agent.knowledge.retrieval import EvidenceRetriever

DSN = os.environ.get(
    "KNOWLEDGE_DATABASE_URL",
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
)


@pytest.fixture
def repo():
    r = KnowledgePgRepository(DSN, application_name="osint-retrieval-tests")
    try:
        r.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"knowledge PG unavailable: {exc}")
    yield r
    r.close()


@pytest.fixture
def ws():
    return f"ret-{uuid.uuid4().hex[:12]}"


def _fake_embed(text: str) -> list[float]:
    # deterministic pseudo-embedding: bag-of-words hashed into 1024 dims
    v = [0.0] * 1024
    for w in text.lower().split():
        v[hash(w) % 1024] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _seed(repo, ws: str) -> dict:
    doc_rpa = repo.add_document(
        source_type="web", title="RPA рынок РФ", url="https://ex/rpa",
        origin_id=f"rpa-{ws}", workspace_id=ws,
    )
    snap = repo.add_snapshot(document_id=doc_rpa, content_hash=f"h-rpa-{ws}", parse_status="ok")
    emb_rpa = _fake_embed("рынок rpa роботизация автоматизация поставщики выручка")
    c_rpa = repo.add_chunk(
        document_id=doc_rpa, snapshot_id=snap,
        text="Объем рынка RPA в России 12 млрд руб. Поставщики: Красный Октябрь, Robotics.",
        content_hash=f"ch-rpa-{ws}", embedding=emb_rpa,
        embedding_model="fake", embedding_revision="r1", preprocessing_version="p1",
    )
    ev_rpa = repo.add_evidence(
        "Объем рынка RPA 12 млрд руб",
        claim_type="fact", document_id=doc_rpa, quote="12 млрд руб", workspace_id=ws,
    )

    doc_soup = repo.add_document(
        source_type="web", title="Кулинария", url="https://ex/soup",
        origin_id=f"soup-{ws}", workspace_id=ws,
    )
    snap2 = repo.add_snapshot(document_id=doc_soup, content_hash=f"h-soup-{ws}", parse_status="ok")
    emb_soup = _fake_embed("рецепт борща говядина свекла сметана")
    repo.add_chunk(
        document_id=doc_soup, snapshot_id=snap2,
        text="Рецепт борща: говядина, свекла, сметана.",
        content_hash=f"ch-soup-{ws}", embedding=emb_soup,
        embedding_model="fake", embedding_revision="r1", preprocessing_version="p1",
    )
    return {"doc_rpa": doc_rpa, "chunk_rpa": c_rpa, "ev_rpa": ev_rpa, "doc_soup": doc_soup}


def test_hybrid_prefers_relevant(repo, ws):
    ids = _seed(repo, ws)
    r = EvidenceRetriever(repo, embed_fn=_fake_embed)
    res = r.retrieve("объем рынка RPA роботизация", workspace_id=ws, mode="hybrid")
    assert res.items, res.empty_reason
    # top hit should be the RPA doc, not soup
    top_docs = [i.document_id for i in res.items[:3]]
    assert ids["doc_rpa"] in top_docs
    assert res.retrieval_id
    assert res.items[0].rank == 1


def test_empty_corpus_reason(repo, ws):
    r = EvidenceRetriever(repo, embed_fn=_fake_embed)
    res = r.retrieve("неведомый вопрос про единорогов", workspace_id=f"empty-{ws}", mode="hybrid")
    assert res.items == []
    assert res.empty_reason == "no_evidence_in_allowed_corpus"


def test_workspace_isolation_r10(repo, ws):
    ids = _seed(repo, ws)
    other = f"other-{ws}"
    r = EvidenceRetriever(repo, embed_fn=_fake_embed)
    res = r.retrieve("рынок RPA", workspace_id=other, mode="hybrid")
    assert res.items == []  # closed doc of another workspace is not returned
    res2 = r.retrieve("рынок RPA", workspace_id=ws, mode="hybrid")
    assert any(i.document_id == ids["doc_rpa"] for i in res2.items)


def test_vector_only_and_text_only(repo, ws):
    ids = _seed(repo, ws)
    r = EvidenceRetriever(repo, embed_fn=_fake_embed)
    v = r.retrieve("роботизация автоматизация", workspace_id=ws, mode="vector")
    assert v.items and v.items[0].origin == "vector"
    t = r.retrieve("12 млрд", workspace_id=ws, mode="text")
    assert t.items and t.items[0].origin == "text"


def test_no_embedding_degrades_with_limitation(repo, ws):
    _seed(repo, ws)
    r = EvidenceRetriever(repo, embed_fn=None)
    res = r.retrieve("рынок RPA", workspace_id=ws, mode="hybrid")
    assert "embedding_service_unavailable" in res.limitations
    assert res.items  # text path still works (§8 limited mode)


def test_dedupe_limits_doc_dominance(repo, ws):
    doc = repo.add_document(source_type="web", title="many", origin_id=f"many-{ws}", workspace_id=ws)
    snap = repo.add_snapshot(document_id=doc, content_hash=f"hm-{ws}", parse_status="ok")
    for i in range(10):
        repo.add_chunk(
            document_id=doc, snapshot_id=snap,
            text=f"рынок RPA фрагмент {i} выручка",
            content_hash=f"chm-{ws}-{i}", embedding=_fake_embed(f"рынок RPA выручка {i}"),
            embedding_model="fake", embedding_revision="r1", preprocessing_version="p1",
        )
    r = EvidenceRetriever(repo, embed_fn=_fake_embed)
    res = r.retrieve("рынок RPA выручка", workspace_id=ws, mode="hybrid")
    per_doc = sum(1 for i in res.items if i.document_id == doc)
    assert per_doc <= 3


def test_min_similarity_drops_weak_vector_and_empty_reason(repo, ws):
    _seed(repo, ws)
    # unrelated question has no lexical overlap and low vector sim → empty (R09)
    r = EvidenceRetriever(repo, embed_fn=_fake_embed, min_similarity=0.99)
    res = r.retrieve("квантовая телепортация сверхпроводимость", workspace_id=ws, mode="vector")
    assert not res.items
    assert res.empty_reason == "no_evidence_in_allowed_corpus"
    # lowering the threshold lets weak vector noise through
    r2 = EvidenceRetriever(repo, embed_fn=_fake_embed, min_similarity=0.0)
    res2 = r2.retrieve("квантовая телепортация сверхпроводимость", workspace_id=ws, mode="vector")
    assert res2.items
