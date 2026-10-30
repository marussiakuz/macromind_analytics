"""PostgreSQL knowledge repository (Task2 RAG §5, §10.1).

DSN via KNOWLEDGE_DATABASE_URL or constructor argument:
  postgresql://user:pass@host:5433/knowledge

Implements persistent entities, documents, snapshots, chunks, evidence,
jobs with lease + fencing token, retrieval_runs and report_versions.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgePgRepository:
    def __init__(self, dsn: str, *, application_name: str = "osint-knowledge"):
        self.dsn = dsn
        self.application_name = application_name
        self._conn: psycopg.Connection | None = None

    def connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                application_name=self.application_name,
                autocommit=False,
            )
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    @contextmanager
    def tx(self) -> Iterator[psycopg.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # --- entities -----------------------------------------------------------

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        identifiers: dict | None = None,
        *,
        workspace_id: str | None = None,
        alt_names: list[str] | None = None,
    ) -> str:
        """Upsert by (type, name, workspace). Identifiers must not auto-merge
        distinct companies (R12): conflicting keys → a new entity row."""
        identifiers = identifiers or {}
        with self.tx() as conn:
            rows = conn.execute(
                """
                SELECT id, identifiers FROM entities
                WHERE entity_type = %s AND name = %s
                  AND COALESCE(workspace_id, '') = COALESCE(%s, '')
                """,
                (entity_type, name, workspace_id),
            ).fetchall()
            conflict_keys = {"inn", "ogrn", "ogrnip", "tax_id", "bin", "le_id"}
            for row in rows:
                existing = dict(row["identifiers"] or {})
                has_conflict = any(
                    k in identifiers and k in existing and identifiers[k] != existing[k]
                    for k in conflict_keys
                )
                if has_conflict:
                    continue
                conn.execute(
                    "UPDATE entities SET identifiers = %s, alt_names = %s WHERE id = %s",
                    (Jsonb({**existing, **identifiers}), Jsonb(alt_names or []), row["id"]),
                )
                return str(row["id"])
            eid = str(uuid4())
            conn.execute(
                """
                INSERT INTO entities (id, entity_type, name, identifiers, alt_names, workspace_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (eid, entity_type, name, Jsonb(identifiers), Jsonb(alt_names or []), workspace_id),
            )
            return eid

    def add_entity_relation(
        self,
        *,
        subject_id: str,
        relation: str,
        object_id: str | None = None,
        object_label: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        evidence_id: str | None = None,
    ) -> str:
        rid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO entity_relations
                  (id, subject_id, relation, object_id, object_label, period_start, period_end, evidence_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (rid, subject_id, relation, object_id, object_label, period_start, period_end, evidence_id),
            )
        return rid

    # --- documents / snapshots ---------------------------------------------

    def add_document(
        self,
        *,
        source_type: str,
        url: str | None = None,
        title: str | None = None,
        origin_id: str | None = None,
        checksum: str | None = None,
        storage_path: str | None = None,
        license: str | None = None,
        metadata: dict | None = None,
        workspace_id: str | None = None,
        published_at: datetime | None = None,
    ) -> str:
        with self.tx() as conn:
            if origin_id:
                # scope origin_id by workspace: closed docs of one project
                # must not become shared via text coincidence (§5)
                row = conn.execute(
                    """
                    SELECT id FROM documents
                    WHERE origin_id = %s
                      AND COALESCE(workspace_id,'') = COALESCE(%s,'')
                    """,
                    (origin_id, workspace_id),
                ).fetchone()
                if row:
                    return str(row["id"])
            did = str(uuid4())
            conn.execute(
                """
                INSERT INTO documents
                  (id, origin_id, source_type, url, title, published_at, storage_path,
                   checksum, license, metadata, workspace_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    did, origin_id, source_type, url, title, published_at,
                    storage_path, checksum, license, Jsonb(metadata or {}), workspace_id,
                ),
            )
            return did

    def add_snapshot(
        self,
        *,
        document_id: str,
        content_hash: str,
        storage_path: str | None = None,
        size_bytes: int | None = None,
        mime_type: str | None = None,
        published_at: datetime | None = None,
        event_at: datetime | None = None,
        coverage: str | None = None,
        parse_status: str = "pending",
        extraction_version: str | None = None,
        error: str | None = None,
    ) -> str:
        """Idempotent by (document_id, content_hash) — R02/R03."""
        with self.tx() as conn:
            row = conn.execute(
                """
                SELECT id FROM source_snapshots
                WHERE document_id = %s AND content_hash = %s
                """,
                (document_id, content_hash),
            ).fetchone()
            if row:
                return str(row["id"])
            sid = str(uuid4())
            conn.execute(
                """
                INSERT INTO source_snapshots
                  (id, document_id, content_hash, storage_path, size_bytes, mime_type,
                   published_at, event_at, coverage, parse_status, extraction_version, error)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    sid, document_id, content_hash, storage_path, size_bytes, mime_type,
                    published_at, event_at, coverage, parse_status, extraction_version, error,
                ),
            )
            return sid

    def update_snapshot_parse(
        self, snapshot_id: str, *, parse_status: str, error: str | None = None,
        extraction_version: str | None = None,
    ) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE source_snapshots
                SET parse_status = %s, error = %s,
                    extraction_version = COALESCE(%s, extraction_version)
                WHERE id = %s
                """,
                (parse_status, error, extraction_version, snapshot_id),
            )

    # --- evidence / chunks --------------------------------------------------

    def add_evidence(
        self,
        statement: str,
        *,
        claim_type: str = "fact",
        document_id: str | None = None,
        entity_id: str | None = None,
        quote: str | None = None,
        locator: str | None = None,
        period: str | None = None,
        geography: str | None = None,
        unit: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        eid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO evidence
                  (id, document_id, entity_id, claim_type, statement, locator, quote,
                   period, geography, unit, workspace_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    eid, document_id, entity_id, claim_type, statement, locator,
                    quote, period, geography, unit, workspace_id,
                ),
            )
        return eid

    def add_chunk(
        self,
        *,
        document_id: str,
        text: str,
        snapshot_id: str | None = None,
        evidence_id: str | None = None,
        lang: str | None = None,
        token_count: int | None = None,
        chunk_index: int | None = None,
        heading: str | None = None,
        page: int | None = None,
        content_hash: str | None = None,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
        preprocessing_version: str | None = None,
        profile_id: str | None = None,
    ) -> str:
        """Chunk + optional vector. Dedupes within the same document (R02)."""
        cid = str(uuid4())
        with self.tx() as conn:
            if content_hash:
                # Dedupe even without embeddings; keep model/revision/preprocess
                # as part of the key so a model swap does not collide (R02/R04).
                row = conn.execute(
                    """
                    SELECT id FROM chunks
                    WHERE document_id = %s AND content_hash = %s
                      AND COALESCE(embedding_model,'') = COALESCE(%s,'')
                      AND COALESCE(embedding_revision,'') = COALESCE(%s,'')
                      AND COALESCE(preprocessing_version,'') = COALESCE(%s,'')
                    """,
                    (document_id, content_hash, embedding_model, embedding_revision, preprocessing_version),
                ).fetchone()
                if row:
                    return str(row["id"])
            emb = None
            if embedding is not None:
                if len(embedding) != 1024:
                    raise ValueError(f"embedding dim {len(embedding)} != 1024")
                if any(not _finite(x) for x in embedding):
                    raise ValueError("embedding contains non-finite numbers")
                emb = "[" + ",".join(f"{float(x):.8g}" for x in embedding) + "]"
            conn.execute(
                """
                INSERT INTO chunks
                  (id, document_id, snapshot_id, evidence_id, text, lang, token_count,
                   chunk_index, heading, page, content_hash,
                   embedding, embedding_model, embedding_revision, preprocessing_version, profile_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s,%s)
                """,
                (
                    cid, document_id, snapshot_id, evidence_id, text, lang, token_count,
                    chunk_index, heading, page, content_hash,
                    emb, embedding_model, embedding_revision, preprocessing_version, profile_id,
                ),
            )
            return cid

    def upsert_chunk_embedding(
        self, *, chunk_id: str, embedding: list[float], embedding_model: str,
        embedding_revision: str, conn: psycopg.Connection | None = None,
    ) -> bool:
        """Fill an existing chunk; never silently replace a different model profile.

        Workers must call this inside publish_embedding_job's fenced transaction.
        A nonexistent chunk is not inserted: its text and provenance are required.
        """
        if (len(embedding) != 1024 or not any(embedding)
                or any(isinstance(x, bool) or not isinstance(x, (float, int))
                       or not _finite(x) for x in embedding)):
            raise ValueError("invalid embedding vector")
        if not embedding_model or not embedding_revision:
            raise ValueError("embedding profile is required")
        if conn is None:
            with self.tx() as transaction:
                return self.upsert_chunk_embedding(
                    chunk_id=chunk_id, embedding=embedding, embedding_model=embedding_model,
                    embedding_revision=embedding_revision, conn=transaction,
                )
        vector = "[" + ",".join(f"{float(x):.8g}" for x in embedding) + "]"
        result = conn.execute(
            """UPDATE chunks SET embedding = %s::vector, embedding_model = %s,
                      embedding_revision = %s
               WHERE id = %s
                 AND (embedding_model IS NULL OR embedding_model = %s)
                 AND (embedding_revision IS NULL OR embedding_revision = %s)""",
            (vector, embedding_model, embedding_revision, chunk_id,
             embedding_model, embedding_revision),
        )
        return result.rowcount == 1

    def publish_embedding_job(
        self, job_id: str, worker: str, fencing_token: int, *,
        chunk_vectors: list[tuple[str, list[float]]], model: str, revision: str,
    ) -> bool:
        """Publish all vectors and completion atomically under the live job lease."""
        with self.tx() as conn:
            job = conn.execute(
                """SELECT id FROM jobs WHERE id = %s AND lease_owner = %s
                   AND fencing_token = %s AND status = 'running' AND NOT cancel_requested
                   AND lease_expires_at > clock_timestamp()
                   AND (deadline_at IS NULL OR deadline_at > clock_timestamp()) FOR UPDATE""",
                (job_id, worker, fencing_token),
            ).fetchone()
            if not job:
                return False
            for chunk_id, vector in chunk_vectors:
                if not self.upsert_chunk_embedding(
                    chunk_id=chunk_id, embedding=vector, embedding_model=model,
                    embedding_revision=revision, conn=conn,
                ):
                    raise ValueError("chunk missing or incompatible embedding profile")
            conn.execute(
                """UPDATE jobs SET status = 'completed', stage = 'indexing', result = %s,
                   error = NULL, error_kind = NULL, finished_at = now(), updated_at = now(),
                   lease_owner = NULL, lease_expires_at = NULL WHERE id = %s""",
                (Jsonb({"embedded": len(chunk_vectors), "stored": len(chunk_vectors),
                        "dimension": 1024, "model": model, "revision": revision}), job_id),
            )
            return True

    def list_evidence(self, entity_id: str | None = None, workspace_id: str | None = None) -> list[dict]:
        with self.tx() as conn:
            sql = "SELECT * FROM evidence WHERE 1=1"
            args: list[Any] = []
            if entity_id:
                sql += " AND entity_id = %s"
                args.append(entity_id)
            if workspace_id is not None:
                sql += " AND COALESCE(workspace_id,'') = %s"
                args.append(workspace_id)
            return list(conn.execute(sql + " ORDER BY created_at DESC", args).fetchall())

    def get_evidence_by_id(
        self,
        evidence_id: str,
        *,
        allowed_workspaces: list[str] | None = None,
    ) -> dict | None:
        """Fetch one evidence by id, scoped to allowed workspaces.

        allowed_workspaces=None → unrestricted (internal service only).
        Empty list → never returns a private row.
        """
        with self.tx() as conn:
            if allowed_workspaces is None:
                row = conn.execute(
                    "SELECT * FROM evidence WHERE id = %s OR id::text = %s",
                    (evidence_id, evidence_id),
                ).fetchone()
                return dict(row) if row else None
            if not allowed_workspaces:
                return None
            ph = ",".join(["%s"] * len(allowed_workspaces))
            row = conn.execute(
                f"""
                SELECT * FROM evidence
                WHERE (id = %s OR id::text = %s)
                  AND COALESCE(workspace_id,'') IN ({ph})
                """,
                (evidence_id, evidence_id, *allowed_workspaces),
            ).fetchone()
            return dict(row) if row else None

    def search_text(
        self,
        query: str,
        limit: int = 10,
        workspace_id: str | None = None,
        *,
        entity_id: str | None = None,
        since=None,
        source_types: list[str] | None = None,
    ) -> list[dict]:
        """Exact-fact lookup. Word OR with ≥half-hit threshold (R07) —
        whole-phrase LIKE misses natural-language questions.

        Filters (workspace/entity/since/source_types) are applied in SQL
        before LIMIT (Astra §6.3).
        """
        words = [w for w in re.findall(r"\w+", query, flags=re.UNICODE) if len(w) >= 2]
        if not words:
            words = [query] if query else []
        if not words:
            return []
        need = max(1, (len(words) + 1) // 2)
        hit_parts = []
        args: list[Any] = []
        for w in words:
            like = f"%{w}%"
            hit_parts.append(
                "(CASE WHEN statement ILIKE %s OR COALESCE(quote,'') ILIKE %s THEN 1 ELSE 0 END)"
            )
            args.extend([like, like])
        hit_expr = " + ".join(hit_parts)
        sql = f"""
            SELECT ev.*, ({hit_expr}) AS hits FROM evidence ev
            LEFT JOIN documents d ON d.id = ev.document_id
            WHERE ({hit_expr}) >= %s
        """
        args.extend(args[: len(words) * 2])  # repeat for WHERE hit_expr
        args.append(need)
        if workspace_id is not None:
            sql += " AND COALESCE(ev.workspace_id,'') = %s"
            args.append(workspace_id)
        if entity_id:
            sql += " AND ev.entity_id = %s"
            args.append(entity_id)
        if since:
            sql += " AND COALESCE(d.published_at, ev.created_at) >= %s"
            args.append(str(since))
        if source_types:
            ph = ",".join(["%s"] * len(source_types))
            sql += f" AND d.source_type IN ({ph})"
            args.extend(list(source_types))
        sql += " ORDER BY hits DESC, ev.created_at DESC LIMIT %s"
        args.append(limit)
        with self.tx() as conn:
            return list(conn.execute(sql, args).fetchall())

    def search_chunks_text(
        self,
        query: str,
        limit: int = 30,
        workspace_id: str | None = None,
        *,
        source_types: list[str] | None = None,
        since=None,
        entity_id: str | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
    ) -> list[dict]:
        """Keyword search over chunk text + document metadata (§8).

        Multi-word queries match if at least half the words hit (OR of ILIKEs
        scored by hit count) — avoids brittle whole-phrase LIKE only.
        Filters are applied in SQL before LIMIT (Astra §6.3).
        """
        words = [w for w in re.findall(r"\w+", query, flags=re.UNICODE) if len(w) >= 2]
        if not words:
            words = [query] if query else []
        if not words:
            return []
        clauses = []
        args: list[Any] = []
        for w in words:
            like = f"%{w}%"
            clauses.append(
                "(c.text ILIKE %s OR COALESCE(c.heading,'') ILIKE %s OR COALESCE(d.title,'') ILIKE %s"
                " OR COALESCE(e.statement,'') ILIKE %s OR COALESCE(e.quote,'') ILIKE %s)"
            )
            args.extend([like, like, like, like, like])
        # require at least ceil(n/2) word hits
        need = max(1, (len(words) + 1) // 2)
        hit_expr = " + ".join(
            f"(CASE WHEN c.text ILIKE %s OR COALESCE(c.heading,'') ILIKE %s"
            f" OR COALESCE(d.title,'') ILIKE %s OR COALESCE(e.statement,'') ILIKE %s"
            f" OR COALESCE(e.quote,'') ILIKE %s THEN 1 ELSE 0 END)"
            for _ in words
        )
        hit_args: list[Any] = []
        for w in words:
            like = f"%{w}%"
            hit_args.extend([like, like, like, like, like])
        where = f"({ ' OR '.join(clauses) }) AND ({hit_expr}) >= %s"
        args.extend(hit_args)
        args.append(need)
        if workspace_id is not None:
            where += " AND COALESCE(d.workspace_id,'') = %s"
            args.append(workspace_id)
        if source_types:
            ph = ",".join(["%s"] * len(source_types))
            where += f" AND d.source_type IN ({ph})"
            args.extend(list(source_types))
        if since:
            where += " AND COALESCE(d.published_at, s.retrieved_at) >= %s"
            args.append(str(since))
        if entity_id:
            where += " AND (e.entity_id = %s OR c.evidence_id IN (SELECT id FROM evidence WHERE entity_id = %s))"
            args.extend([entity_id, entity_id])
        if embedding_model:
            where += " AND (c.embedding_model IS NULL OR c.embedding_model = %s)"
            args.append(embedding_model)
        if embedding_revision:
            where += " AND (c.embedding_revision IS NULL OR c.embedding_revision = %s)"
            args.append(embedding_revision)
        sql = f"""
            SELECT c.id AS chunk_id, c.document_id, c.snapshot_id, c.evidence_id,
                   c.text, c.heading, c.page, c.embedding_model, c.embedding_revision,
                   d.title, d.url, d.published_at, d.source_type, d.metadata,
                   e.verification_status, e.statement, e.quote
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN source_snapshots s ON s.id = c.snapshot_id
            LEFT JOIN evidence e ON e.id = c.evidence_id
            WHERE {where}
            ORDER BY {hit_expr} DESC
            LIMIT %s
        """
        args.extend(hit_args)  # ORDER BY placeholders
        args.append(int(limit))
        with self.tx() as conn:
            rows = conn.execute(sql, args).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["excerpt"] = (d.pop("text") or "")[:500]
                out.append(d)
            return out

    def vector_search(
        self,
        embedding: list[float],
        *,
        limit: int = 30,
        workspace_id: str | None = None,
        min_similarity: float | None = None,
        source_types: list[str] | None = None,
        since=None,
        entity_id: str | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
    ) -> list[dict]:
        """Cosine similarity over chunks; exact scan first (§8 — index later).

        Access + entity + period + model/revision filters are applied in SQL
        before results leave the database and before LIMIT (Astra §6.3).
        """
        if len(embedding) != 1024:
            raise ValueError(f"embedding dim {len(embedding)} != 1024")
        emb = "[" + ",".join(f"{float(x):.8g}" for x in embedding) + "]"
        where_parts = ["c.embedding IS NOT NULL"]
        fargs: list[Any] = []
        if workspace_id is not None:
            where_parts.append("COALESCE(d.workspace_id,'') = %s")
            fargs.append(workspace_id)
        if min_similarity is not None:
            where_parts.append("(1 - (c.embedding <=> %s::vector)) >= %s")
            fargs.extend([emb, float(min_similarity)])
        if source_types:
            ph = ",".join(["%s"] * len(source_types))
            where_parts.append(f"d.source_type IN ({ph})")
            fargs.extend(list(source_types))
        if since:
            where_parts.append("COALESCE(d.published_at, s.retrieved_at) >= %s")
            fargs.append(str(since))
        if entity_id:
            where_parts.append(
                "(e.entity_id = %s OR c.evidence_id IN (SELECT id FROM evidence WHERE entity_id = %s))"
            )
            fargs.extend([entity_id, entity_id])
        # Never mix vectors of incompatible model/revision profiles (Astra §6.3)
        if embedding_model:
            where_parts.append("c.embedding_model = %s")
            fargs.append(embedding_model)
        if embedding_revision:
            where_parts.append("c.embedding_revision = %s")
            fargs.append(embedding_revision)
        where_sql = " AND ".join(where_parts)
        sql = f"""
            SELECT c.id AS chunk_id, c.document_id, c.snapshot_id, c.evidence_id,
                   c.text, c.heading, c.page, c.lang,
                   c.embedding_model, c.embedding_revision,
                   d.title, d.url, d.published_at, d.source_type, d.metadata,
                   e.verification_status,
                   1 - (c.embedding <=> %s::vector) AS sim
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            LEFT JOIN source_snapshots s ON s.id = c.snapshot_id
            LEFT JOIN evidence e ON e.id = c.evidence_id
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        # placeholders: 1) SELECT sim, 2..n) filters, n+1) ORDER BY, last) LIMIT
        args = [emb] + fargs + [emb, int(limit)]
        with self.tx() as conn:
            rows = conn.execute(sql, args).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["excerpt"] = (d.pop("text") or "")[:500]
                out.append(d)
            return out

    # --- jobs (lease + fencing) --------------------------------------------

    def create_job(
        self,
        job_type: str,
        *,
        run_id: str | None = None,
        stage: str = "collecting",
        payload: dict | None = None,
        retry_key: str | None = None,
        deadline_at: datetime | None = None,
        max_attempts: int = 2,
    ) -> str:
        jid = str(uuid4())
        deadline_at = deadline_at or (_now() + timedelta(minutes=30))
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        with self.tx() as conn:
            if retry_key:
                row = conn.execute(
                    "SELECT id FROM jobs WHERE retry_key = %s", (retry_key,)
                ).fetchone()
                if row:
                    return str(row["id"])
            conn.execute(
                """
                INSERT INTO jobs (id, job_type, run_id, stage, payload, retry_key, deadline_at, max_attempts)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (jid, job_type, run_id, stage, Jsonb(payload or {}), retry_key, deadline_at, max_attempts),
            )
        return jid

    def set_document_index_status(
        self,
        document_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> bool:
        """Astra §6.3 p.6: saved | indexing | ready | error | cancelled."""
        if status not in {"saved", "indexing", "ready", "error", "cancelled"}:
            raise ValueError(f"invalid index_status {status}")
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE documents
                SET index_status = %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                """,
                (status, Jsonb({"index_error": error} if error else {}), document_id),
            )
            return row.rowcount == 1

    def get_document_index_status(self, document_id: str) -> dict | None:
        with self.tx() as conn:
            row = conn.execute(
                "SELECT id, index_status, metadata FROM documents WHERE id = %s",
                (document_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_document(self, document_id: str, *, workspace_id: str | None = None) -> dict | None:
        """Read-back for §7: metadata, original URL, checksum, index_status."""
        with self.tx() as conn:
            sql = "SELECT * FROM documents WHERE id = %s OR id::text = %s"
            args: list[Any] = [document_id, document_id]
            if workspace_id is not None:
                sql += " AND COALESCE(workspace_id,'') = %s"
                args.append(workspace_id)
            row = conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def get_document_by_origin(self, origin_id: str, *, workspace_id: str | None = None) -> dict | None:
        with self.tx() as conn:
            sql = "SELECT * FROM documents WHERE origin_id = %s"
            args: list[Any] = [origin_id]
            if workspace_id is not None:
                sql += " AND COALESCE(workspace_id,'') = %s"
                args.append(workspace_id)
            row = conn.execute(sql + " LIMIT 1", args).fetchone()
            return dict(row) if row else None

    def count_chunks_with_text(self, document_id: str) -> dict:
        """§7: PDF must yield extracted text, not filename-only stubs."""
        with self.tx() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS n_chunks,
                       count(*) FILTER (WHERE length(coalesce(text,'')) > 40) AS n_with_text,
                       coalesce(max(length(coalesce(text,''))), 0) AS max_text_len
                FROM chunks WHERE document_id = %s
                """,
                (document_id,),
            ).fetchone()
            return dict(row) if row else {"n_chunks": 0, "n_with_text": 0, "max_text_len": 0}

    def claim_job(
        self,
        worker: str,
        *,
        lease_seconds: int = 120,
        job_type: str | None = None,
        job_id: str | None = None,
    ) -> dict | None:
        """FOR UPDATE SKIP LOCKED + lease + fencing token bump.

        Honours next_attempt_at so released jobs wait out their backoff (§6.3 p.7).
        """
        filters = ""
        args: list[Any] = [worker, lease_seconds]
        if job_type:
            filters += " AND job_type = %s"
            args.append(job_type)
        if job_id:
            filters += " AND id = %s"
            args.append(job_id)
        with self.tx() as conn:
            row = conn.execute(
                f"""
                UPDATE jobs
                SET status = 'running',
                    lease_owner = %s,
                    lease_expires_at = now() + make_interval(secs => %s),
                    fencing_token = fencing_token + 1,
                    attempts = attempts + 1,
                    started_at = COALESCE(started_at, now()),
                    updated_at = now(),
                    next_attempt_at = NULL
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE (status = 'queued'
                       OR (status = 'running' AND lease_expires_at < now()))
                      AND NOT cancel_requested AND attempts < max_attempts
                      AND (deadline_at IS NULL OR deadline_at > now())
                      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                      {filters}
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING *
                """,
                args,
            ).fetchone()
            return dict(row) if row else None

    def renew_lease(self, job_id: str, worker: str, fencing_token: int, *, lease_seconds: int = 120) -> bool:
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET lease_expires_at = now() + make_interval(secs => %s), updated_at = now()
                WHERE id = %s AND lease_owner = %s AND fencing_token = %s AND status = 'running'
                  AND NOT cancel_requested AND lease_expires_at > clock_timestamp()
                  AND (deadline_at IS NULL OR deadline_at > clock_timestamp())
                """,
                (lease_seconds, job_id, worker, fencing_token),
            )
            return row.rowcount == 1

    def finish_job(
        self,
        job_id: str,
        worker: str,
        fencing_token: int,
        *,
        status: str,
        result: dict | None = None,
        error: str | None = None,
        error_kind: str | None = None,
        stage: str | None = None,
    ) -> bool:
        """Atomic publish: stale worker after fencing bump cannot write (R19)."""
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET status = %s,
                    result = %s,
                    error = %s,
                    error_kind = %s,
                    stage = COALESCE(%s, stage),
                    finished_at = now(),
                    updated_at = now(),
                    lease_owner = NULL,
                    lease_expires_at = NULL
                WHERE id = %s AND lease_owner = %s AND fencing_token = %s
                  AND status = 'running' AND NOT cancel_requested
                  AND lease_expires_at > clock_timestamp()
                  AND (deadline_at IS NULL OR deadline_at > clock_timestamp())
                """,
                (status, Jsonb(result) if result is not None else None, error, error_kind,
                 stage, job_id, worker, fencing_token),
            )
            return row.rowcount == 1

    def release_job(
        self,
        job_id: str,
        worker: str,
        fencing_token: int,
        *,
        error: str | None = None,
        error_kind: str | None = None,
        backoff_seconds: int | None = None,
    ) -> bool:
        """Return a leased job to the queue (retryable failure). Bumps fencing
        so the previous owner cannot publish after release.

        backoff_seconds: delay before the next claim (§6.3 p.7).
        Default is 2^(attempts-1)*5s (5, 10, 20…), capped at 5 minutes.
        """
        with self.tx() as conn:
            if backoff_seconds is None:
                row = conn.execute(
                    "SELECT attempts FROM jobs WHERE id = %s", (job_id,)
                ).fetchone()
                attempt = int(row["attempts"]) if row else 1
                backoff_seconds = min(300, 5 * (2 ** max(0, attempt - 1)))
            row = conn.execute(
                """
                UPDATE jobs
                SET status = 'queued',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error = %s,
                    error_kind = %s,
                    fencing_token = fencing_token + 1,
                    next_attempt_at = now() + make_interval(secs => %s),
                    updated_at = now()
                WHERE id = %s AND lease_owner = %s AND fencing_token = %s AND status = 'running'
                  AND NOT cancel_requested AND lease_expires_at > clock_timestamp()
                  AND (deadline_at IS NULL OR deadline_at > clock_timestamp())
                """,
                (error, error_kind, int(backoff_seconds), job_id, worker, fencing_token),
            )
            return row.rowcount == 1

    def request_cancel(self, job_id: str) -> bool:
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET cancel_requested = true,
                    fencing_token = fencing_token + 1,
                    status = CASE WHEN status IN ('queued','running','waiting_for_input')
                                  THEN 'cancelled' ELSE status END,
                    finished_at = now(), lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = now()
                WHERE id = %s AND status IN ('queued','running','waiting_for_input')
                """,
                (job_id,),
            )
            return row.rowcount == 1

    def is_cancelled(self, job_id: str) -> bool:
        with self.tx() as conn:
            row = conn.execute(
                "SELECT cancel_requested, status FROM jobs WHERE id = %s", (job_id,)
            ).fetchone()
            return bool(row and (row["cancel_requested"] or row["status"] == "cancelled"))

    def get_job(self, job_id: str) -> dict | None:
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
            return dict(row) if row else None

    def sweep_expired_jobs(self) -> int:
        """Server-1 reaper: enforce deadlines even when server 2 stays offline."""
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET status = CASE WHEN attempts >= max_attempts OR deadline_at <= now()
                                  THEN 'failed' ELSE 'queued' END,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    fencing_token = fencing_token + 1,
                    error = CASE WHEN deadline_at <= now() THEN 'job deadline exceeded'
                                 WHEN attempts >= max_attempts THEN COALESCE(error, 'attempt limit reached')
                                 ELSE error END,
                    error_kind = CASE WHEN deadline_at <= now() THEN 'deadline'
                                      WHEN attempts >= max_attempts THEN 'job' ELSE error_kind END,
                    finished_at = CASE WHEN attempts >= max_attempts OR deadline_at <= now()
                                       THEN now() ELSE NULL END,
                    updated_at = now()
                WHERE status IN ('queued', 'running', 'waiting_for_input')
                  AND (deadline_at <= now()
                       OR (status IN ('queued', 'running') AND attempts >= max_attempts
                           AND (status = 'queued' OR lease_expires_at < now()))
                       OR (status = 'running' AND lease_expires_at < now()))
                """
            )
            return row.rowcount

    # --- retrieval / reports ------------------------------------------------

    def save_retrieval_run(
        self,
        *,
        question: str,
        mode: str = "hybrid",
        filters: dict | None = None,
        candidates: list | None = None,
        selected: list | None = None,
        scores: dict | None = None,
        limitations: list | None = None,
        index_profile: str | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        rid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO retrieval_runs
                  (id, question, filters, mode, candidates, selected, scores, limitations,
                   index_profile, embedding_model, embedding_revision, workspace_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    rid, question, Jsonb(filters or {}), mode,
                    Jsonb(candidates or []), Jsonb(selected or []), Jsonb(scores or {}),
                    Jsonb(limitations or []), index_profile, embedding_model,
                    embedding_revision, workspace_id,
                ),
            )
        return rid

    def save_report_version(
        self,
        *,
        study_id: str,
        report_version: int,
        body: dict,
        content_hash: str,
        evidence_ids: list | None = None,
        chunk_ids: list | None = None,
        calculation_ids: list | None = None,
        model_uri: str | None = None,
        instruction_version: str | None = None,
        validator_version: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        rid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO report_versions
                  (id, study_id, report_version, body_json, evidence_ids, chunk_ids,
                   calculation_ids, model_uri, instruction_version, validator_version,
                   content_hash, workspace_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (study_id, report_version) DO NOTHING
                RETURNING id
                """,
                (
                    rid, study_id, report_version, Jsonb(body),
                    Jsonb(evidence_ids or []), Jsonb(chunk_ids or []), Jsonb(calculation_ids or []),
                    model_uri, instruction_version, validator_version, content_hash, workspace_id,
                ),
            )
            row = conn.execute(
                "SELECT id FROM report_versions WHERE study_id=%s AND report_version=%s",
                (study_id, report_version),
            ).fetchone()
            return str(row["id"])

    def get_report_version(self, study_id: str, report_version: int) -> dict | None:
        with self.tx() as conn:
            row = conn.execute(
                "SELECT * FROM report_versions WHERE study_id=%s AND report_version=%s",
                (study_id, report_version),
            ).fetchone()
            return dict(row) if row else None

    # --- analysis versions (Task1 migration target) -------------------------

    def save_analysis_version(
        self,
        *,
        version: int,
        status: str,
        summary: dict,
        legal_entity_inn: str | None = None,
        study_id: str | None = None,
        request_key: str | None = None,
    ) -> str:
        vid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO analysis_versions_k
                  (id, study_id, legal_entity_inn, version, status, summary_json, request_key)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (vid, study_id, legal_entity_inn, version, status, Jsonb(summary), request_key),
            )
        return vid

    def latest_analysis_version(self, legal_entity_inn: str) -> dict | None:
        with self.tx() as conn:
            row = conn.execute(
                """
                SELECT * FROM analysis_versions_k
                WHERE legal_entity_inn = %s
                ORDER BY version DESC LIMIT 1
                """,
                (legal_entity_inn,),
            ).fetchone()
            return dict(row) if row else None

    # --- weak signals (§11) ------------------------------------------------

    def insert_watchlist(
        self,
        *,
        topic: str,
        products: list | None = None,
        technologies: list | None = None,
        companies: list | None = None,
        queries: list | None = None,
        geography: list | None = None,
        budget: dict | None = None,
        schedule_cron: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        wid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO watchlists
                  (id, workspace_id, topic, products, technologies, companies,
                   queries, geography, budget_json, schedule_cron)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    wid, workspace_id, topic,
                    Jsonb(products or []), Jsonb(technologies or []),
                    Jsonb(companies or []), Jsonb(queries or []),
                    Jsonb(geography or []), Jsonb(budget or {}), schedule_cron,
                ),
            )
        return wid

    def upsert_signal_event(
        self,
        *,
        event_type: str,
        subject: str,
        technology: str | None = None,
        company: str | None = None,
        geography: str | None = None,
        event_at=None,
        published_at=None,
        source_document_id: str | None = None,
        source_evidence_id: str | None = None,
        reprint_cluster_id: str | None = None,
        notes: str | None = None,
        workspace_id: str | None = None,
        watchlist_id: str | None = None,
        increment_independent: bool = True,
    ) -> dict:
        """Same reprint_cluster_id does not inflate independent_sources (R15)."""
        with self.tx() as conn:
            if reprint_cluster_id:
                row = conn.execute(
                    """
                    SELECT * FROM signal_events
                    WHERE reprint_cluster_id = %s
                      AND COALESCE(workspace_id,'') = COALESCE(%s,'')
                    LIMIT 1
                    """,
                    (reprint_cluster_id, workspace_id),
                ).fetchone()
                if row:
                    if increment_independent and source_document_id and str(
                        row.get("source_document_id") or ""
                    ) != str(source_document_id):
                        conn.execute(
                            """
                            UPDATE signal_events
                            SET independent_sources = independent_sources + 1
                            WHERE id = %s
                            """,
                            (row["id"],),
                        )
                        row = conn.execute(
                            "SELECT * FROM signal_events WHERE id = %s", (row["id"],)
                        ).fetchone()
                    return dict(row)
            eid = str(uuid4())
            conn.execute(
                """
                INSERT INTO signal_events
                  (id, workspace_id, watchlist_id, event_type, subject, technology,
                   company, geography, event_at, published_at,
                   source_document_id, source_evidence_id, reprint_cluster_id, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    eid, workspace_id, watchlist_id, event_type, subject, technology,
                    company, geography, event_at, published_at,
                    source_document_id, source_evidence_id, reprint_cluster_id, notes,
                ),
            )
            row = conn.execute("SELECT * FROM signal_events WHERE id = %s", (eid,)).fetchone()
            return dict(row)

    def link_reprint(
        self,
        primary_event_id: str,
        source_document_id: str | None,
        cluster_id: str,
    ) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE signal_events
                SET reprint_cluster_id = COALESCE(reprint_cluster_id, %s)
                WHERE id = %s
                """,
                (cluster_id, primary_event_id),
            )
            # reprint does not bump independent_sources

    def list_signal_events(
        self,
        *,
        workspace_id: str | None = None,
        since=None,
        limit: int = 50,
    ) -> list[dict]:
        sql = "SELECT * FROM signal_events WHERE 1=1"
        args: list[Any] = []
        if workspace_id is not None:
            sql += " AND COALESCE(workspace_id,'') = %s"
            args.append(workspace_id)
        if since is not None:
            sql += " AND COALESCE(event_at, published_at, detected_at::date) >= %s"
            args.append(since)
        sql += " ORDER BY COALESCE(event_at, published_at, detected_at::date) DESC LIMIT %s"
        args.append(int(limit))
        with self.tx() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def count_signal_events(self, *, workspace_id: str | None, start, end) -> int:
        sql = """
            SELECT count(*) AS n FROM signal_events
            WHERE COALESCE(event_at, published_at, detected_at::date) BETWEEN %s AND %s
        """
        args: list[Any] = [start, end]
        if workspace_id is not None:
            sql += " AND COALESCE(workspace_id,'') = %s"
            args.append(workspace_id)
        with self.tx() as conn:
            return int(conn.execute(sql, args).fetchone()["n"])

    def insert_signal_hypothesis(
        self,
        *,
        statement: str,
        status: str = "unverified",
        evidence_ids: list | None = None,
        event_ids: list | None = None,
        window_start=None,
        window_end=None,
        baseline_start=None,
        baseline_end=None,
        limitations: list | None = None,
        alternatives: list | None = None,
        questions: list | None = None,
        coverage_limited: bool = False,
        workspace_id: str | None = None,
        watchlist_id: str | None = None,
        extra_notes: str | None = None,
    ) -> dict:
        lim = list(limitations or [])
        if extra_notes:
            lim.append(extra_notes)
        hid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO signal_hypotheses
                  (id, workspace_id, watchlist_id, statement, status, evidence_ids,
                   event_ids, window_start, window_end, baseline_start, baseline_end,
                   limitations, alternatives, questions, coverage_limited)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    hid, workspace_id, watchlist_id, statement, status,
                    Jsonb([str(x) for x in (evidence_ids or [])]),
                    Jsonb([str(x) for x in (event_ids or [])]),
                    window_start, window_end, baseline_start, baseline_end,
                    Jsonb(lim), Jsonb(alternatives or []), Jsonb(questions or []),
                    coverage_limited,
                ),
            )
            row = conn.execute("SELECT * FROM signal_hypotheses WHERE id = %s", (hid,)).fetchone()
            return dict(row)

    def list_signal_hypotheses(self, *, workspace_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM signal_hypotheses"
        args: list[Any] = []
        if workspace_id is not None:
            sql += " WHERE COALESCE(workspace_id,'') = %s"
            args.append(workspace_id)
        sql += " ORDER BY created_at DESC"
        with self.tx() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def insert_research_binding(
        self,
        *,
        project_ref: str | None = None,
        legal_entity_inn: str | None = None,
        product_ref: str | None = None,
        analysis_version_id: str | None = None,
        report_version_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str:
        bid = str(uuid4())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO research_bindings
                  (id, workspace_id, project_ref, legal_entity_inn, product_ref,
                   report_version_id, analysis_version_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    bid, workspace_id, project_ref, legal_entity_inn, product_ref,
                    report_version_id, analysis_version_id,
                ),
            )
        return bid


def _finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def repository_from_env() -> KnowledgePgRepository:
    import os

    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("KNOWLEDGE_DATABASE_URL is not set")
    return KnowledgePgRepository(dsn)
