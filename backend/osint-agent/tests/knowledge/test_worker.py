"""Real PostgreSQL state transitions; embedding HTTP is controlled, never paid.

Set KNOWLEDGE_DATABASE_URL to an isolated database with migrations applied.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from osint_agent.knowledge.embeddings import EmbeddingClient
from osint_agent.knowledge.pg_repository import KnowledgePgRepository
from osint_agent.knowledge.worker import KnowledgeJobWorker


@pytest.fixture
def repo():
    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        pytest.skip("Set KNOWLEDGE_DATABASE_URL to an isolated migrated test database")
    repository = KnowledgePgRepository(dsn, application_name="knowledge-worker-tests")
    repository.connect()  # Explicitly requested integration runs must fail, not skip on errors.
    yield repository
    repository.close()


def seed(repo, count=2):
    doc = repo.add_document(source_type="file", workspace_id=f"worker-{uuid4()}")
    ids = [repo.add_chunk(document_id=doc, text=f"saved text {i}") for i in range(count)]
    kind = "embed_chunks"  # worker accepts only its own type
    jid = repo.create_job(kind, payload={"chunk_ids": ids}, max_attempts=2)
    return jid, ids


def stored(repo, ids):
    with repo.tx() as conn:
        return [
            conn.execute("SELECT embedding FROM chunks WHERE id=%s", (cid,)).fetchone()["embedding"]
            for cid in ids
        ]


def client(handler):
    transport = httpx.MockTransport(handler)
    return EmbeddingClient("http://embedding.test", client=httpx.AsyncClient(transport=transport))


def ok(value=0.01):
    return httpx.Response(
        200, json={"vectors": [[value] * 1024], "revision": "r1", "dimension": 1024}
    )


@pytest.mark.asyncio
async def test_success_stores_correct_vectors(repo):
    jid, ids = seed(repo)

    def respond(request):
        import json

        text = json.loads(request.content)["texts"][0]
        return ok(0.01 if text.endswith("0") else 0.02)

    emb = client(respond)
    worker = KnowledgeJobWorker(repo, emb)
    result = await worker.run_once(job_id=jid)
    assert result == {"job_id": jid, "status": "completed", "error_kind": None}
    assert repo.get_job(jid)["result"]["stored"] == 2
    assert "0.01" in str(stored(repo, ids)[0])
    assert "0.02" in str(stored(repo, ids)[1])
    await emb._client.aclose()


def ready_for_retry(repo, jid):
    """Clear backoff so the next run_once can claim immediately (tests only)."""
    with repo.tx() as conn:
        conn.execute(
            "UPDATE jobs SET next_attempt_at = NULL WHERE id=%s", (jid,)
        )


@pytest.mark.asyncio
async def test_server_down_exhausts_retries(repo):
    jid, ids = seed(repo)

    def unavailable(request):
        raise httpx.ConnectError("down", request=request)

    emb = client(unavailable)
    worker = KnowledgeJobWorker(repo, emb)
    assert (await worker.run_once(job_id=jid))["status"] == "queued"
    ready_for_retry(repo, jid)
    assert (await worker.run_once(job_id=jid))["status"] == "failed"
    assert repo.get_job(jid)["attempts"] == 2
    assert repo.get_job(jid)["error_kind"] == "embedding_unavailable"
    assert stored(repo, ids) == [None, None]
    await emb._client.aclose()


@pytest.mark.asyncio
async def test_transient_failure_then_success(repo):
    jid, ids = seed(repo, 1)
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls == 1 else ok()

    emb = client(respond)
    worker = KnowledgeJobWorker(repo, emb)
    assert (await worker.run_once(job_id=jid))["status"] == "queued"
    ready_for_retry(repo, jid)
    assert (await worker.run_once(job_id=jid))["status"] == "completed"
    assert stored(repo, ids)[0] is not None
    await emb._client.aclose()


@pytest.mark.asyncio
async def test_cancel_during_request_publishes_no_vectors(repo):
    jid, ids = seed(repo)

    def respond(request):
        repo.request_cancel(jid)
        return ok()

    emb = client(respond)
    result = await KnowledgeJobWorker(repo, emb).run_once(job_id=jid)
    assert result["status"] == "cancelled"
    assert stored(repo, ids) == [None, None]
    await emb._client.aclose()


@pytest.mark.asyncio
async def test_missing_chunk_never_shifts_vector_mapping(repo):
    jid, ids = seed(repo)
    with repo.tx() as conn:
        conn.execute("DELETE FROM chunks WHERE id=%s", (ids[0],))
    calls = []
    emb = client(lambda request: calls.append(request) or ok())
    assert (await KnowledgeJobWorker(repo, emb).run_once(job_id=jid))["status"] == "failed"
    assert calls == []
    assert stored(repo, ids[1:]) == [None]
    await emb._client.aclose()


def test_stale_worker_cannot_write_vectors(repo):
    jid, ids = seed(repo, 1)
    a = repo.claim_job("old", job_id=jid)
    with repo.tx() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s", (jid,)
        )
    b = repo.claim_job("new", job_id=jid)
    assert b["fencing_token"] > a["fencing_token"]
    assert not repo.publish_embedding_job(
        jid,
        "old",
        a["fencing_token"],
        chunk_vectors=[(ids[0], [0.01] * 1024)],
        model="m",
        revision="r",
    )
    assert stored(repo, ids) == [None]
    repo.request_cancel(jid)


def test_expired_lease_cannot_publish_even_without_new_owner(repo):
    jid, ids = seed(repo, 1)
    a = repo.claim_job("old", job_id=jid)
    with repo.tx() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s", (jid,)
        )
    assert not repo.renew_lease(jid, "old", a["fencing_token"])
    assert not repo.publish_embedding_job(
        jid,
        "old",
        a["fencing_token"],
        chunk_vectors=[(ids[0], [0.01] * 1024)],
        model="m",
        revision="r",
    )
    repo.request_cancel(jid)


def test_deadline_reaper_handles_queued_job_with_server2_offline(repo):
    jid = repo.create_job(
        "embed_chunks", deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    assert repo.claim_job("w", job_id=jid) is None
    repo.sweep_expired_jobs()
    assert repo.get_job(jid)["status"] == "failed"
    assert repo.get_job(jid)["error_kind"] == "deadline"


def test_atomic_rollback_on_missing_second_chunk(repo):
    jid, ids = seed(repo)
    a = repo.claim_job("w", job_id=jid)
    with pytest.raises(ValueError):
        repo.publish_embedding_job(
            jid,
            "w",
            a["fencing_token"],
            chunk_vectors=[(ids[0], [0.01] * 1024), (str(uuid4()), [0.02] * 1024)],
            model="m",
            revision="r",
        )
    assert stored(repo, ids) == [None, None]
    repo.request_cancel(jid)


def test_different_embedding_profile_is_not_overwritten(repo):
    jid, ids = seed(repo, 1)
    assert repo.upsert_chunk_embedding(
        chunk_id=ids[0], embedding=[0.01] * 1024, embedding_model="old", embedding_revision="old"
    )
    a = repo.claim_job("w", job_id=jid)
    with pytest.raises(ValueError):
        repo.publish_embedding_job(
            jid,
            "w",
            a["fencing_token"],
            chunk_vectors=[(ids[0], [0.02] * 1024)],
            model="new",
            revision="new",
        )
    with repo.tx() as conn:
        assert (
            conn.execute("SELECT embedding_model FROM chunks WHERE id=%s", (ids[0],)).fetchone()[
                "embedding_model"
            ]
            == "old"
        )
    repo.request_cancel(jid)
