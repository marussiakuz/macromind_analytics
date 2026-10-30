"""Durable embedding worker and independent server-1 deadline sweeper.

Run `python -m osint_agent.knowledge.worker --help` for the service entrypoint.
No vectors become visible until the complete, fenced job transaction commits.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any

from osint_agent.knowledge.embeddings import DIM, EmbeddingClient
from osint_agent.knowledge.env import apply_knowledge_env
from osint_agent.knowledge.pg_repository import KnowledgePgRepository

log = logging.getLogger(__name__)
RETRYABLE = {"timeout", "unavailable", "rate_limited", "not_ready", "error"}


class KnowledgeJobWorker:
    def __init__(
        self,
        repo: KnowledgePgRepository,
        embed: EmbeddingClient | None = None,
        worker_id: str | None = None,
    ):
        self.repo = repo
        self.embed = embed or EmbeddingClient()
        self.worker_id = worker_id or f"knowledge-worker-{os.getpid()}"

    def _state(self, job: dict) -> dict:
        current = self.repo.get_job(job["id"])
        return {
            "job_id": str(job["id"]),
            "status": current["status"] if current else "missing",
            "error_kind": current.get("error_kind") if current else None,
        }

    def _retry_or_fail(self, job: dict, error: str, kind: str, retryable: bool) -> dict:
        args = (job["id"], self.worker_id, job["fencing_token"])
        if retryable and job["attempts"] < job["max_attempts"]:
            self.repo.release_job(*args, error=error, error_kind=kind)
        else:
            self.repo.finish_job(*args, status="failed", error=error, error_kind=kind)
            self._mark_doc(job, "error", error=error)
        self.repo.sweep_expired_jobs()
        return self._state(job)

    def _mark_doc(self, job: dict, status: str, *, error: str | None = None) -> None:
        doc_id = (job.get("payload") or {}).get("document_id")
        if doc_id:
            try:
                self.repo.set_document_index_status(doc_id, status, error=error)
            except Exception:  # noqa: BLE001
                log.warning("failed to set index_status=%s for %s", status, doc_id)

    async def run_once(
        self,
        *,
        job_type: str | None = "embed_chunks",
        job_id: str | None = None,
    ) -> dict[str, Any] | None:
        self.repo.sweep_expired_jobs()
        job = self.repo.claim_job(
            self.worker_id, job_type=job_type, job_id=job_id, lease_seconds=120
        )
        if job is None:
            return None
        try:
            if job["job_type"] != "embed_chunks":
                raise ValueError("unsupported job type")
            return await self._embed_chunks(job)
        except (ValueError, TypeError, KeyError):
            return self._retry_or_fail(
                job, "Invalid embedding job input or response", "invalid_input", False
            )
        except Exception as exc:
            # Do not expose connection strings or document contents via raw exceptions.
            log.error("knowledge job %s failed (%s)", job["id"], type(exc).__name__)
            return self._retry_or_fail(job, "Embedding job failed", "job", False)

    async def _embed_chunks(self, job: dict) -> dict:
        chunk_ids = (job.get("payload") or {}).get("chunk_ids")
        if (
            not isinstance(chunk_ids, list)
            or not chunk_ids
            or len(chunk_ids) > 256
            or any(not isinstance(cid, str) for cid in chunk_ids)
            or len(set(chunk_ids)) != len(chunk_ids)
        ):
            raise ValueError("expected 1..256 unique chunk IDs")
        # Always read saved text. Filtering missing rows would shift vector-to-ID mapping.
        with self.repo.tx() as conn:
            texts = []
            for cid in chunk_ids:
                row = conn.execute("SELECT text FROM chunks WHERE id = %s", (cid,)).fetchone()
                if not row or not row["text"].strip():
                    raise ValueError("missing or empty chunk")
                texts.append(row["text"])
        vectors = []
        revision = None
        for cid, text in zip(chunk_ids, texts):
            if not self.repo.renew_lease(job["id"], self.worker_id, job["fencing_token"]):
                self.repo.sweep_expired_jobs()
                return self._state(job)
            # One request is bounded by the HTTP timeout; renew before every next chunk.
            result = await self.embed.embed([text], input_type="document")
            if not result.ok:
                code = result.error_code or "error"
                kind = (
                    "embedding_unavailable"
                    if code in {"timeout", "unavailable", "not_ready"}
                    else "embedding_error"
                )
                return self._retry_or_fail(job, result.error or code, kind, code in RETRYABLE)
            if result.dimension != DIM or len(result.vectors) != 1 or not result.revision:
                raise ValueError("bad embedding response")
            if revision is not None and result.revision != revision:
                raise ValueError("model changed during job")
            revision = result.revision
            vectors.append((cid, result.vectors[0]))
        self.repo.publish_embedding_job(
            job["id"],
            self.worker_id,
            job["fencing_token"],
            chunk_vectors=vectors,
            model=os.environ.get("EMBEDDING_MODEL") or "Qwen/Qwen3-Embedding-0.6B",
            revision=revision,
        )
        self._mark_doc(job, "ready")
        self.repo.sweep_expired_jobs()
        return self._state(job)


def build_worker(dsn: str | None = None) -> KnowledgeJobWorker:
    apply_knowledge_env()
    dsn = dsn or os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("KNOWLEDGE_DATABASE_URL is not set")
    return KnowledgeJobWorker(KnowledgePgRepository(dsn))


async def _serve(args: argparse.Namespace) -> None:
    worker = build_worker()
    try:
        while True:
            if args.reaper_only:
                worker.repo.sweep_expired_jobs()
            else:
                await worker.run_once()
            if args.once:
                break
            await asyncio.sleep(max(1.0, args.interval))
    finally:
        await worker.embed.aclose()
        worker.repo.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reaper-only", action="store_true", help="Run on server 1 independently of server 2"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    try:
        asyncio.run(_serve(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
