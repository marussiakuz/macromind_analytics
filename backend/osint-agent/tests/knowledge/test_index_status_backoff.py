"""Astra §6.3 leftovers: document index_status + retry backoff."""

from __future__ import annotations

import os
import uuid

import pytest

from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.ingestion import Ingester
from osint_agent.knowledge.pg_repository import KnowledgePgRepository


def _repo() -> KnowledgePgRepository:
    dsn = os.environ.get(
        "KNOWLEDGE_DATABASE_URL",
        "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
    )
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


def test_ingest_sets_indexing_status_and_jobs(repo, ws, tmp_path):
    ing = Ingester(repo, ObjectStore(str(tmp_path / "o")))
    res = ing.ingest_bytes(
        b"Document for index status check about logistics.",
        title="idx", workspace_id=ws, mime_type="text/plain",
    )
    assert res.job_ids
    st = repo.get_document_index_status(res.document_id)
    assert st["index_status"] == "indexing"


def test_failed_parse_sets_error_status(repo, ws, tmp_path):
    ing = Ingester(repo, ObjectStore(str(tmp_path / "o")))
    # empty application/pdf without text layer
    res = ing.ingest_bytes(
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF",
        title="pdf-empty", workspace_id=ws, mime_type="application/pdf",
        origin_id=f"pdf-{ws}",
    )
    if res.parse_status != "ok":
        st = repo.get_document_index_status(res.document_id)
        assert st["index_status"] == "error"


def test_release_job_sets_backoff(repo, ws):
    jid = repo.create_job("embed_chunks", payload={"chunk_ids": ["x"]}, max_attempts=3)
    claimed = repo.claim_job("w1", job_id=jid)
    assert claimed
    assert repo.release_job(jid, "w1", claimed["fencing_token"], error="tmp", error_kind="job")
    # must not be claimable immediately (backoff)
    assert repo.claim_job("w2", job_id=jid) is None
    with repo.tx() as conn:
        conn.execute(
            "UPDATE jobs SET next_attempt_at = now() - interval '1 second' WHERE id=%s",
            (jid,),
        )
    again = repo.claim_job("w2", job_id=jid)
    assert again is not None
    assert again["attempts"] == 2


def test_index_status_transitions(repo, ws):
    doc = repo.add_document(source_type="file", origin_id=f"st-{ws}", workspace_id=ws)
    assert repo.set_document_index_status(doc, "indexing")
    assert repo.get_document_index_status(doc)["index_status"] == "indexing"
    assert repo.set_document_index_status(doc, "ready")
    assert repo.get_document_index_status(doc)["index_status"] == "ready"
    with pytest.raises(ValueError):
        repo.set_document_index_status(doc, "nope")
