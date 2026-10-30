"""Live R26: server 2 down → terminal job status; reports stay readable.

Run from repository/osint-agent with tunnels up (15432/18091):
  ./.venv/bin/python scripts/r26_live_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_agent.knowledge.env import apply_knowledge_env  # noqa: E402
from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402
from osint_agent.knowledge.worker import KnowledgeJobWorker  # noqa: E402
from osint_agent.knowledge.embeddings import EmbeddingClient  # noqa: E402


def emit(rid: str, status: str, detail: str) -> None:
    print(json.dumps({"id": rid, "status": status, "detail": detail}, ensure_ascii=False))


class DeadEmbed(EmbeddingClient):
    """Simulates server 2 unreachable."""

    async def embed(self, texts, input_type="document"):
        import httpx
        try:
            return await super().embed(texts, input_type=input_type)
        except Exception:
            pass
        # Force connection-style failure via a dead port
        self.base_url = "http://127.0.0.1:9"  # discard port
        return await super().embed(texts, input_type=input_type)


async def main() -> int:
    apply_knowledge_env()
    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        emit("ENV", "fail", "KNOWLEDGE_DATABASE_URL missing")
        return 1
    repo = KnowledgePgRepository(dsn)
    ws = f"r26-{uuid.uuid4().hex[:8]}"

    # --- seed a chunk + embed job ---------------------------------------
    doc = repo.add_document(source_type="file", title="R26 probe", workspace_id=ws)
    snap = repo.add_snapshot(document_id=doc, content_hash="r26", parse_status="ok")
    cid = repo.add_chunk(
        document_id=doc, snapshot_id=snap, text="R26 probe text for embedding",
        content_hash="r26c", token_count=5, chunk_index=0,
    )
    jid = repo.create_job(
        "embed_chunks",
        stage="indexing",
        payload={"chunk_ids": [cid], "document_id": doc},
        retry_key=f"r26-{ws}",
        max_attempts=2,
    )
    emit("R26-SETUP", "pass", f"job={jid} chunk={cid[:8]}")

    # --- server 2 down: worker must reach terminal failed ---------------
    dead = EmbeddingClient("http://127.0.0.1:9")
    worker = KnowledgeJobWorker(repo, dead, worker_id=f"r26-worker-{ws}")

    r1 = await worker.run_once(job_id=jid)
    j_after1 = repo.get_job(jid)
    emit("R26-TRY1", "pass" if r1 and r1["status"] in {"queued", "failed"} else "fail",
         f"first={r1} attempts={j_after1['attempts']} status={j_after1['status']} err={j_after1.get('error_kind')}")

    r2 = await worker.run_once(job_id=jid)
    j_after2 = repo.get_job(jid)
    terminal = j_after2["status"] == "failed"
    kind = j_after2.get("error_kind") or ""
    emit(
        "R26-TERMINAL",
        "pass" if terminal else "fail",
        f"status={j_after2['status']} error_kind={kind} "
        f"error={str(j_after2.get('error'))[:80]} attempts={j_after2['attempts']}",
    )

    # no vectors published while server2 down
    with repo.tx() as conn:
        row = conn.execute("SELECT embedding FROM chunks WHERE id=%s", (cid,)).fetchone()
    no_vec = row is not None and row["embedding"] is None
    emit("R26-NO-VECTORS", "pass" if no_vec else "fail", f"embedding_is_null={no_vec}")

    # --- reports remain readable without server 2 -----------------------
    vid = repo.save_report_version(
        study_id=f"r26-study-{ws}",
        report_version=1,
        body={"title": "R26 saved report", "sections": []},
        content_hash="r26rep",
        workspace_id=ws,
    )
    got = repo.get_report_version(f"r26-study-{ws}", 1)
    emit(
        "R26-REPORTS-READABLE",
        "pass" if got and got.get("content_hash") == "r26rep" else "fail",
        f"report_version_id={vid[:8] if vid else None} readable={bool(got)}",
    )

    # search degrades honestly (text still works, vector empty)
    from osint_agent.knowledge.retrieval import EvidenceRetriever

    def empty_embed(q: str) -> list[float]:
        return []

    res = EvidenceRetriever(repo, embed_fn=empty_embed).retrieve(
        "R26 probe text", mode="vector", workspace_id=ws, limit=5
    )
    emit(
        "R26-SEARCH-DEGRADES",
        "pass" if res.empty_reason or res.limitations else "fail",
        f"empty_reason={res.empty_reason} limitations={res.limitations}",
    )

    # --- independent reaper: expired lease → terminal after max_attempts -
    jid2 = repo.create_job(
        "embed_chunks",
        payload={"chunk_ids": [cid]},
        retry_key=f"r26-reaper-{ws}",
        max_attempts=1,
    )
    claimed = repo.claim_job("dead-worker", job_id=jid2, lease_seconds=1)
    with repo.tx() as conn:
        conn.execute(
            "UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id=%s",
            (jid2,),
        )
    swept = repo.sweep_expired_jobs()
    j2 = repo.get_job(jid2)
    emit(
        "R26-REAPER",
        "pass" if j2["status"] == "failed" else "fail",
        f"swept={swept} status={j2['status']} error_kind={j2.get('error_kind')} attempts={j2['attempts']}",
    )

    await dead.aclose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"id": "R26-CRASH", "status": "fail", "detail": repr(exc)}))
        raise SystemExit(2)
