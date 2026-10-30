"""Postgres repository + ingestion tests (Task2 Stage B).

Uses local macromind-knowledge-pg (127.0.0.1:5433) when available.
Skipped when KNOWLEDGE_DATABASE_URL is unset and docker PG is unreachable.
"""

from __future__ import annotations

import os
import uuid

import pytest

from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.ingestion import Ingester, split_chunks
from osint_agent.knowledge.pg_repository import KnowledgePgRepository

DSN = os.environ.get(
    "KNOWLEDGE_DATABASE_URL",
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
)


def _repo() -> KnowledgePgRepository:
    r = KnowledgePgRepository(DSN, application_name="osint-knowledge-tests")
    try:
        r.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"knowledge PG unavailable: {exc}")
    return r


@pytest.fixture
def repo():
    r = _repo()
    yield r
    r.close()


@pytest.fixture
def ws():
    return f"test-{uuid.uuid4().hex[:12]}"


def test_entity_upsert_and_relation(repo, ws):
    a = repo.upsert_entity("org", "ООО Рога", {"inn": "7701"}, workspace_id=ws)
    b = repo.upsert_entity("org", "ООО Рога", {"inn": "7701"}, workspace_id=ws)
    assert a == b
    other = repo.upsert_entity("org", "ООО Рога", {"inn": "7702"}, workspace_id=f"{ws}-2")
    assert other != a  # R12: same name, different workspace → not merged
    rid = repo.add_entity_relation(subject_id=a, relation="customer", object_label="Заказчик-1")
    assert rid


def test_entity_same_name_different_inn_not_merged(repo, ws):
    """R12: distinct identifiers must not auto-merge companies."""
    a = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "1111111111"}, workspace_id=ws)
    b = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "2222222222"}, workspace_id=ws)
    assert a != b
    # same inn still upserts to the same row
    c = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "1111111111"}, workspace_id=ws)
    assert c == a


def test_document_origin_dedupe(repo, ws):
    d1 = repo.add_document(source_type="web", url="https://a", origin_id="rep-x", workspace_id=ws)
    d2 = repo.add_document(source_type="web", url="https://b", origin_id="rep-x", workspace_id=ws)
    assert d1 == d2


def test_snapshot_same_hash_idempotent(repo, ws):
    doc = repo.add_document(source_type="file", origin_id=f"o-{ws}", workspace_id=ws)
    s1 = repo.add_snapshot(document_id=doc, content_hash="abc123", parse_status="ok")
    s2 = repo.add_snapshot(document_id=doc, content_hash="abc123", parse_status="ok")
    assert s1 == s2
    s3 = repo.add_snapshot(document_id=doc, content_hash="abc124", parse_status="ok")
    assert s3 != s1  # R03 new content → new snapshot


def test_chunk_embedding_dim_and_dedupe(repo, ws):
    doc = repo.add_document(source_type="file", origin_id=f"c-{ws}", workspace_id=ws)
    snap = repo.add_snapshot(document_id=doc, content_hash="h1", parse_status="ok")
    emb = [0.001] * 1024
    c1 = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="фрагмент", content_hash="ch1",
        embedding=emb, embedding_model="qwen3-emb-0.6b", embedding_revision="r1",
        preprocessing_version="extract-0.1",
    )
    c2 = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="фрагмент", content_hash="ch1",
        embedding=emb, embedding_model="qwen3-emb-0.6b", embedding_revision="r1",
        preprocessing_version="extract-0.1",
    )
    assert c1 == c2
    # R02: dedupe must work without embeddings too
    n1 = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="без вектора", content_hash="ch-noemb",
        token_count=2, chunk_index=0,
    )
    n2 = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="без вектора", content_hash="ch-noemb",
        token_count=2, chunk_index=0,
    )
    assert n1 == n2
    # different model → different vector key (R04)
    c3 = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="фрагмент", content_hash="ch1",
        embedding=emb, embedding_model="qwen3-emb-other", embedding_revision="r1",
        preprocessing_version="extract-0.1",
    )
    assert c3 != c1
    with pytest.raises(ValueError):
        repo.add_chunk(
            document_id=doc, snapshot_id=snap, text="bad", content_hash="ch2",
            embedding=[0.1] * 10, embedding_model="m", embedding_revision="r",
            preprocessing_version="p",
        )
    with pytest.raises(ValueError):
        repo.add_chunk(
            document_id=doc, snapshot_id=snap, text="bad", content_hash="ch3",
            embedding=[float("nan")] * 1024, embedding_model="m", embedding_revision="r",
            preprocessing_version="p",
        )


def test_job_lease_fencing_and_cancel(repo, ws):
    jid = repo.create_job("collect", payload={"q": "x"}, retry_key=f"rk-{ws}")
    dup = repo.create_job("collect", payload={"q": "x"}, retry_key=f"rk-{ws}")
    assert jid == dup  # R20

    claimed = repo.claim_job("worker-1", job_id=jid)
    assert claimed is not None
    tok = claimed["fencing_token"]
    assert claimed["status"] == "running"

    # second worker cannot claim same job while lease valid
    assert repo.claim_job("worker-2", job_id=jid) is None

    # stale fencing token cannot finish (R19)
    assert repo.finish_job(jid, "worker-1", tok + 99, status="completed") is False
    assert repo.finish_job(jid, "worker-1", tok, status="completed", result={"ok": True}) is True

    # cancel bumps fencing (R41)
    j2 = repo.create_job("index", retry_key=f"rk2-{ws}")
    c = repo.claim_job("worker-3", job_id=j2)
    assert c and str(c["id"]) == j2
    assert repo.request_cancel(j2) is True
    assert repo.is_cancelled(j2) is True
    assert repo.finish_job(j2, "worker-3", c["fencing_token"], status="completed") is False


def test_retrieval_and_report_versions(repo, ws):
    rid = repo.save_retrieval_run(
        question="объем рынка RPA",
        mode="hybrid",
        selected=[{"chunk_id": "x", "score": 0.9}],
        limitations=["test"],
        workspace_id=ws,
    )
    assert rid
    body = {"title": "Отчет", "sections": []}
    vid = repo.save_report_version(
        study_id=f"st-{ws}", report_version=1, body=body, content_hash="hh",
        workspace_id=ws,
    )
    assert vid
    got = repo.get_report_version(f"st-{ws}", 1)
    assert got is not None
    assert got["content_hash"] == "hh"
    # idempotent version (R23 reopen without regen)
    again = repo.save_report_version(
        study_id=f"st-{ws}", report_version=1, body=body, content_hash="hh", workspace_id=ws,
    )
    assert again == vid


def test_split_chunks_long_text_no_silent_truncation():
    long = ("Раздел рынка. " * 400 + "\n\n") * 3
    chunks = split_chunks(long)
    assert len(chunks) >= 3
    joined_len = sum(len(c["text"]) for c in chunks)
    assert joined_len >= len(long) * 0.8  # R05: not silently truncated
    assert all(c["content_hash"] for c in chunks)


def test_ingest_bytes_with_object_store(tmp_path, repo, ws):
    store = ObjectStore(tmp_path / "objects")
    ing = Ingester(repo, store)
    payload = "Название: отчет.\n\nОбъем рынка 12 млрд руб в 2025 году.".encode("utf-8")
    res = ing.ingest_bytes(
        payload,
        source_type="file",
        title="Отчет",
        mime_type="text/plain",
        filename="report.txt",
        workspace_id=ws,
    )
    assert res.parse_status == "ok"
    assert res.snapshot_id
    assert res.chunk_ids
    # re-ingest same bytes → same document/snapshot, no extra chunks (R02)
    res2 = ing.ingest_bytes(
        payload,
        source_type="file",
        title="Отчет",
        mime_type="text/plain",
        filename="report.txt",
        workspace_id=ws,
    )
    assert res2.document_id == res.document_id
    assert res2.snapshot_id == res.snapshot_id
    # object exists and verifies
    obj_hash = store.manifest()[0]["content_hash"]
    assert store.verify(obj_hash)


def test_analysis_version_roundtrip(repo, ws):
    vid = repo.save_analysis_version(
        version=1, status="done", summary={"ok": True}, legal_entity_inn=f"INN-{ws}",
    )
    assert vid
    latest = repo.latest_analysis_version(f"INN-{ws}")
    assert latest is not None
    assert latest["summary_json"]["ok"] is True
