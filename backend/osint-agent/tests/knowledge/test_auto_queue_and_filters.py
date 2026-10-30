"""Astra §6.3: auto embed queue + search filters before LIMIT."""

from __future__ import annotations

import uuid

import pytest

from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.ingestion import Ingester
from osint_agent.knowledge.pg_repository import KnowledgePgRepository

DSN = (
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge"
)


def _repo() -> KnowledgePgRepository:
    import os
    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL", DSN)
    r = KnowledgePgRepository(dsn, application_name="osint-tests")
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


@pytest.fixture
def ing(repo, tmp_path):
    return Ingester(repo, ObjectStore(str(tmp_path / "objects")))


def test_ingest_enqueues_embed_jobs(repo, ws, ing, tmp_path):
    res = ing.ingest_bytes(
        b"RPA market grew 30% in 2024 according to the study.",
        title="auto-queue",
        workspace_id=ws,
        mime_type="text/plain",
    )
    assert res.chunk_ids
    assert res.job_ids, "ingest must enqueue embed_chunks jobs (Astra §6.3)"
    job = repo.get_job(res.job_ids[0])
    assert job["job_type"] == "embed_chunks"
    assert job["payload"]["chunk_ids"] == res.chunk_ids
    assert job["status"] == "queued"

    # idempotent: second ingest of the same bytes reuses the same job
    res2 = ing.ingest_bytes(
        b"RPA market grew 30% in 2024 according to the study.",
        title="auto-queue",
        workspace_id=ws,
        mime_type="text/plain",
    )
    assert res2.job_ids == res.job_ids


def test_search_source_type_filter_in_sql(repo, ws, ing):
    ing.ingest_bytes(b"Document about RPA vendors and automation.",
                    title="web doc", workspace_id=ws, source_type="web", mime_type="text/plain")
    ing.ingest_bytes(b"Document about RPA vendors and automation.",
                    title="bench doc", workspace_id=ws, source_type="bench", mime_type="text/plain",
                    origin_id=f"bench-{ws}")
    only_web = repo.search_chunks_text("RPA vendors", workspace_id=ws, source_types=["web"])
    assert only_web and all(r["source_type"] == "web" for r in only_web)
    only_bench = repo.search_chunks_text("RPA vendors", workspace_id=ws, source_types=["bench"])
    assert only_bench and all(r["source_type"] == "bench" for r in only_bench)


def test_search_since_filter(repo, ws, ing):
    from datetime import datetime, timedelta, timezone
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ing.ingest_bytes(b"Old RPA report from 2020.",
                    title="old", workspace_id=ws, mime_type="text/plain",
                    origin_id=f"old-{ws}", published_at=old)
    ing.ingest_bytes(b"New RPA report from 2026.",
                    title="new", workspace_id=ws, mime_type="text/plain",
                    origin_id=f"new-{ws}",
                    published_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    since = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = repo.search_chunks_text("RPA report", workspace_id=ws, since=since)
    titles = {r["title"] for r in rows}
    assert "new" in titles
    assert "old" not in titles


def test_vector_search_model_filter(repo, ws):
    doc = repo.add_document(source_type="file", origin_id=f"m-{ws}", workspace_id=ws)
    snap = repo.add_snapshot(document_id=doc, content_hash="h", parse_status="ok")
    emb = [0.001] * 1024
    repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="alpha product launch",
        content_hash="c1", embedding=emb,
        embedding_model="qwen3-emb-a", embedding_revision="r1",
        preprocessing_version="p",
    )
    repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="alpha product launch",
        content_hash="c2", embedding=emb,
        embedding_model="qwen3-emb-b", embedding_revision="r1",
        preprocessing_version="p",
    )
    rows_a = repo.vector_search(emb, workspace_id=ws, embedding_model="qwen3-emb-a")
    assert rows_a and all(r["embedding_model"] == "qwen3-emb-a" for r in rows_a)
    rows_b = repo.vector_search(emb, workspace_id=ws, embedding_model="qwen3-emb-b")
    assert rows_b and all(r["embedding_model"] == "qwen3-emb-b" for r in rows_b)
    assert {r["chunk_id"] for r in rows_a}.isdisjoint({r["chunk_id"] for r in rows_b})
