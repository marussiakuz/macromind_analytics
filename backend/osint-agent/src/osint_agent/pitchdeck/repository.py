"""SQLite index plus per-analysis folders for uploaded decks and slide images."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from osint_agent.pitchdeck.models import DeckAnalysis

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  done_slides INTEGER NOT NULL DEFAULT 0,
  total_slides INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  result_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PitchDeckRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "pitchdeck.db"
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def folder(self, analysis_id: str) -> Path:
        return self.root / analysis_id

    def create(self, filename: str, suffix: str, content: bytes) -> str:
        analysis_id = str(uuid4())
        folder = self.folder(analysis_id)
        folder.mkdir(parents=True)
        (folder / f"deck{suffix}").write_bytes(content)
        now = _now()
        with self._connect() as db:
            db.execute(
                "INSERT INTO analyses (id, filename, status, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                (analysis_id, filename, now, now),
            )
        return analysis_id

    def deck_path(self, analysis_id: str) -> Path | None:
        folder = self.folder(analysis_id)
        for suffix in (".pdf", ".pptx"):
            path = folder / f"deck{suffix}"
            if path.exists():
                return path
        return None

    def slide_path(self, analysis_id: str, number: int) -> Path:
        return self.folder(analysis_id) / f"slide-{number}.png"

    def set_progress(self, analysis_id: str, done: int, total: int) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE analyses SET status='running', done_slides=?, total_slides=?, updated_at=? WHERE id=?",
                (done, total, _now(), analysis_id),
            )

    def set_done(self, analysis_id: str, result: DeckAnalysis) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE analyses SET status='done', done_slides=total_slides, result_json=?, updated_at=? WHERE id=?",
                (result.model_dump_json(), _now(), analysis_id),
            )

    def set_failed(self, analysis_id: str, code: str, message: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE analyses SET status='failed', error_code=?, error_message=?, updated_at=? WHERE id=?",
                (code, message, _now(), analysis_id),
            )

    def fail_interrupted(self) -> int:
        """A restart loses in-process jobs: show them as failed rather than running forever."""
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE analyses SET status='failed', error_code='interrupted', "
                "error_message='Обработка прервана перезапуском сервиса', updated_at=? "
                "WHERE status IN ('queued', 'running')",
                (_now(),),
            )
            return cursor.rowcount

    @staticmethod
    def _row(row: sqlite3.Row, with_result: bool) -> dict[str, Any]:
        data = {
            "id": row["id"],
            "filename": row["filename"],
            "status": row["status"],
            "done_slides": row["done_slides"],
            "total_slides": row["total_slides"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if with_result:
            data["result"] = json.loads(row["result_json"]) if row["result_json"] else None
        return data

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        return self._row(row, True) if row else None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r, False) for r in rows]

    def delete(self, analysis_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
        shutil.rmtree(self.folder(analysis_id), ignore_errors=True)
        return cursor.rowcount > 0
