"""SQLite→Postgres-ready repository for knowledge entities (Stage A/B).

Until PostgreSQL is available on 10.77.0.1, use file SQLite with same shape.
Postgres DSN via KNOWLEDGE_DATABASE_URL.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  name TEXT NOT NULL,
  identifiers TEXT NOT NULL DEFAULT '{}',
  alt_names TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  origin_id TEXT,
  source_type TEXT NOT NULL,
  url TEXT,
  title TEXT,
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  storage_path TEXT,
  checksum TEXT,
  license TEXT,
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  document_id TEXT,
  entity_id TEXT,
  claim_type TEXT NOT NULL DEFAULT 'fact',
  statement TEXT NOT NULL,
  locator TEXT,
  quote TEXT,
  period TEXT,
  geography TEXT,
  unit TEXT,
  verification_status TEXT NOT NULL DEFAULT 'unreviewed',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  evidence_id TEXT,
  text TEXT NOT NULL,
  lang TEXT,
  token_count INTEGER,
  embedding_json TEXT
);
CREATE TABLE IF NOT EXISTS research_runs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT,
  input_hash TEXT,
  budget TEXT,
  error TEXT,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doc_origin ON documents(origin_id);
CREATE INDEX IF NOT EXISTS idx_ev_entity ON evidence(entity_id);
"""


class KnowledgeRepository:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def upsert_entity(self, entity_type: str, name: str, identifiers: dict | None = None) -> str:
        conn = self.connect()
        # F: устойчивый id по (type, name) — без дублей
        row = conn.execute(
            "SELECT id FROM entities WHERE entity_type=? AND name=?",
            (entity_type, name),
        ).fetchone()
        eid = row["id"] if row else str(uuid4())
        if row:
            conn.execute("UPDATE entities SET identifiers=? WHERE id=?", (json.dumps(identifiers or {}), eid))
        else:
            conn.execute(
                "INSERT INTO entities (id, entity_type, name, identifiers, alt_names, created_at)"
                " VALUES (?,?,?,?,?,datetime('now'))",
                (eid, entity_type, name, json.dumps(identifiers or {}), "[]"),
            )
        conn.commit()
        return eid

    def add_document(self, *, source_type: str, url: str | None, title: str | None,
                     origin_id: str | None = None, checksum: str | None = None,
                     storage_path: str | None = None) -> str:
        conn = self.connect()
        if origin_id:
            row = conn.execute("SELECT id FROM documents WHERE origin_id=?", (origin_id,)).fetchone()
            if row:
                return row["id"]  # F19 перепечатки
        did = str(uuid4())
        conn.execute(
            "INSERT INTO documents (id, origin_id, source_type, url, title, retrieved_at, storage_path, checksum)"
            " VALUES (?,?,?,?,?,datetime('now'),?,?)",
            (did, origin_id, source_type, url, title, storage_path, checksum),
        )
        conn.commit()
        return did

    def add_evidence(self, statement: str, *, claim_type: str = "fact",
                     document_id: str | None = None, entity_id: str | None = None,
                     quote: str | None = None, locator: str | None = None) -> str:
        conn = self.connect()
        eid = str(uuid4())
        conn.execute(
            "INSERT INTO evidence (id, document_id, entity_id, claim_type, statement, locator, quote, verification_status, created_at)"
            " VALUES (?,?,?,?,?,?,?, 'unreviewed', datetime('now'))",
            (eid, document_id, entity_id, claim_type, statement, locator, quote),
        )
        conn.commit()
        return eid

    def list_evidence(self, entity_id: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        if entity_id:
            rows = conn.execute("SELECT * FROM evidence WHERE entity_id=?", (entity_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM evidence").fetchall()
        return [dict(r) for r in rows]

    def search_text(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Точный/текстовый поиск до векторного (Stage D)."""
        conn = self.connect()
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM evidence WHERE statement LIKE ? OR quote LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [dict(r) for r in rows]
