"""SQLite storage for market studies (plan §5 «Хранение»)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from osint_agent.market.models import (
    MarketScope,
    Money,
    Observation,
    StudyPassport,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS studies (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  owner TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  as_of TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  money_basis_currency TEXT NOT NULL DEFAULT 'RUB',
  notes TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  study_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value TEXT,
  unit TEXT NOT NULL,
  geography TEXT,
  reference_period TEXT,
  source_id TEXT NOT NULL,
  source_locator TEXT,
  status TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  FOREIGN KEY(study_id) REFERENCES studies(id)
);
CREATE TABLE IF NOT EXISTS bindings (
  id TEXT PRIMARY KEY,
  study_id TEXT NOT NULL,
  product_scope_id TEXT,
  project_id TEXT,
  legal_entity_inn TEXT,
  report_version INTEGER,
  binding_revision INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY(study_id) REFERENCES studies(id)
);
CREATE INDEX IF NOT EXISTS idx_obs_study ON observations(study_id);
CREATE INDEX IF NOT EXISTS idx_bind_study ON bindings(study_id);
CREATE INDEX IF NOT EXISTS idx_bind_inn ON bindings(legal_entity_inn);
CREATE TABLE IF NOT EXISTS analysis_versions (
  id TEXT PRIMARY KEY,
  study_id TEXT,
  legal_entity_inn TEXT,
  product_scope_id TEXT,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  request_key TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_jobs (
  id TEXT PRIMARY KEY,
  study_id TEXT,
  legal_entity_inn TEXT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  step TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  owner_token TEXT,
  error TEXT,
  result_version_id TEXT,
  started_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_av_inn ON analysis_versions(legal_entity_inn);
CREATE INDEX IF NOT EXISTS idx_av_study ON analysis_versions(study_id);
CREATE INDEX IF NOT EXISTS idx_job_token ON research_jobs(owner_token);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class MarketRepository:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- studies ---

    def create_study(self, passport: StudyPassport) -> StudyPassport:
        conn = self.connect()
        conn.execute(
            "INSERT INTO studies (id, title, owner, scope_json, as_of, version, money_basis_currency, notes, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(passport.id),
                passport.title,
                passport.owner,
                _dump(passport.scope.model_dump()),
                passport.as_of.isoformat() if passport.as_of else None,
                passport.version,
                passport.money_basis_currency,
                passport.notes,
                passport.created_at.isoformat(),
            ),
        )
        conn.commit()
        return passport

    def get_study(self, study_id: UUID | str) -> StudyPassport | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM studies WHERE id = ?", (str(study_id),)).fetchone()
        if row is None:
            return None
        scope = MarketScope.model_validate(json.loads(row["scope_json"]))
        return StudyPassport(
            id=UUID(row["id"]),
            title=row["title"],
            owner=row["owner"],
            scope=scope,
            as_of=datetime.fromisoformat(row["as_of"]).date() if row["as_of"] else None,
            version=row["version"],
            money_basis_currency=row["money_basis_currency"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_studies(self, owner: str | None = None, limit: int = 50, offset: int = 0) -> list[StudyPassport]:
        conn = self.connect()
        sql = "SELECT id FROM studies"
        args: list[Any] = []
        if owner:
            sql += " WHERE owner = ?"
            args.append(owner)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        out: list[StudyPassport] = []
        for row in conn.execute(sql, args).fetchall():
            study = self.get_study(row["id"])
            if study:
                out.append(study)
        return out

    def update_scope(self, study_id: UUID | str, scope: MarketScope, expected_version: int) -> StudyPassport | None:
        """PATCH паспорта с контролем ожидаемой версии (plan §15)."""
        conn = self.connect()
        study = self.get_study(study_id)
        if study is None:
            return None
        if study.version != expected_version:
            raise VersionConflict(study.version)
        conn.execute(
            "UPDATE studies SET scope_json = ?, version = version + 1 WHERE id = ?",
            (_dump(scope.model_dump()), str(study_id)),
        )
        conn.commit()
        return self.get_study(study_id)

    # --- observations ---

    def add_observation(self, study_id: UUID | str, observation: Observation) -> Observation:
        conn = self.connect()
        conn.execute(
            "INSERT INTO observations (id, study_id, metric, value, unit, geography, reference_period,"
            " source_id, source_locator, status, captured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(observation.id),
                str(study_id),
                observation.metric,
                None if observation.value is None else format(observation.value, "f"),
                observation.unit,
                observation.geography,
                observation.reference_period,
                observation.source_id,
                observation.source_locator,
                observation.status.value,
                observation.captured_at.isoformat(),
            ),
        )
        conn.commit()
        return observation

    def list_observations(self, study_id: UUID | str) -> list[Observation]:
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM observations WHERE study_id = ? ORDER BY captured_at", (str(study_id),)
        ).fetchall()
        return [
            Observation(
                id=UUID(r["id"]),
                metric=r["metric"],
                value=Decimal(r["value"]) if r["value"] is not None else None,
                unit=r["unit"],
                geography=r["geography"],
                reference_period=r["reference_period"],
                source_id=r["source_id"],
                source_locator=r["source_locator"],
                status=r["status"],
                captured_at=datetime.fromisoformat(r["captured_at"]),
            )
            for r in rows
        ]

    def set_observation_status(self, study_id: UUID | str, observation_id: UUID | str, status: str) -> bool:
        conn = self.connect()
        cur = conn.execute(
            "UPDATE observations SET status = ? WHERE id = ? AND study_id = ?",
            (status, str(observation_id), str(study_id)),
        )
        conn.commit()
        return cur.rowcount > 0

    # --- bindings ---

    def create_binding(
        self,
        study_id: UUID | str,
        *,
        product_scope_id: str | None = None,
        project_id: str | None = None,
        legal_entity_inn: str | None = None,
        report_version: int | None = None,
    ) -> str:
        binding_id = str(uuid4())
        conn = self.connect()
        conn.execute(
            "INSERT INTO bindings (id, study_id, product_scope_id, project_id, legal_entity_inn, report_version,"
            " binding_revision, created_at) VALUES (?,?,?,?,?,?,1,?)",
            (
                binding_id,
                str(study_id),
                product_scope_id,
                project_id,
                legal_entity_inn,
                report_version,
                _now(),
            ),
        )
        conn.commit()
        return binding_id

    def list_bindings(
        self,
        *,
        legal_entity_inn: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Фильтр по юрлицу может вернуть несколько привязок (plan §15)."""
        conn = self.connect()
        sql = "SELECT * FROM bindings WHERE 1=1"
        args: list[Any] = []
        if legal_entity_inn:
            sql += " AND legal_entity_inn = ?"
            args.append(legal_entity_inn)
        if project_id:
            sql += " AND project_id = ?"
            args.append(project_id)
        sql += " ORDER BY created_at"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]

    # --- analysis versions (Stage B, F23/F30/F31) ---

    def next_analysis_version(self, legal_entity_inn: str | None, study_id: str | None) -> int:
        conn = self.connect()
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM analysis_versions"
            " WHERE (legal_entity_inn IS ? OR legal_entity_inn = ?)"
            " AND (study_id IS ? OR study_id = ?)",
            (legal_entity_inn, legal_entity_inn, study_id, study_id),
        ).fetchone()
        return int(row["v"]) + 1

    def save_analysis_version(
        self,
        summary: dict[str, Any],
        *,
        status: str = "completed",
        request_key: str | None = None,
    ) -> dict[str, Any]:
        version_id = str(uuid4())
        inn = summary.get("legal_entity_inn")
        study_id = summary.get("study_id")
        version = self.next_analysis_version(inn, study_id)
        payload = dict(summary)
        payload["report_version"] = version
        payload["analysis_version_id"] = version_id
        conn = self.connect()
        conn.execute(
            "INSERT INTO analysis_versions"
            " (id, study_id, legal_entity_inn, product_scope_id, version, status, summary_json, request_key, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                version_id,
                study_id,
                inn,
                summary.get("product_scope_id"),
                version,
                status,
                _dump(payload),
                request_key,
                _now(),
            ),
        )
        conn.commit()
        return payload

    def get_analysis_version(self, version_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT summary_json FROM analysis_versions WHERE id = ?", (version_id,)
        ).fetchone()
        return json.loads(row["summary_json"]) if row else None

    def latest_analysis_for(self, legal_entity_inn: str | None = None, study_id: str | None = None) -> dict[str, Any] | None:
        conn = self.connect()
        sql = "SELECT summary_json FROM analysis_versions WHERE 1=1"
        args: list[Any] = []
        if legal_entity_inn:
            sql += " AND legal_entity_inn = ?"
            args.append(legal_entity_inn)
        if study_id:
            sql += " AND study_id = ?"
            args.append(study_id)
        sql += " ORDER BY version DESC LIMIT 1"
        row = conn.execute(sql, args).fetchone()
        return json.loads(row["summary_json"]) if row else None

    def list_analysis_versions(self, legal_entity_inn: str | None = None) -> list[dict[str, Any]]:
        conn = self.connect()
        sql = "SELECT id, version, status, created_at, legal_entity_inn, study_id FROM analysis_versions"
        args: list[Any] = []
        if legal_entity_inn:
            sql += " WHERE legal_entity_inn = ?"
            args.append(legal_entity_inn)
        sql += " ORDER BY version DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]

    # --- research jobs (Stage B, F24/F32) ---

    def create_job(
        self,
        *,
        kind: str,
        legal_entity_inn: str | None = None,
        study_id: str | None = None,
        owner_token: str | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid4())
        now = _now()
        conn = self.connect()
        conn.execute(
            "INSERT INTO research_jobs (id, study_id, legal_entity_inn, kind, status, step, owner_token, started_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, study_id, legal_entity_inn, kind, "running", "started", owner_token, now, now),
        )
        conn.commit()
        return {"id": job_id, "status": "running", "kind": kind}

    def finish_job(self, job_id: str, *, status: str, result_version_id: str | None = None, error: str | None = None) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE research_jobs SET status=?, result_version_id=?, error=?, updated_at=? WHERE id=?",
            (status, result_version_id, error, _now(), job_id),
        )
        conn.commit()

    def job_by_token(self, owner_token: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM research_jobs WHERE owner_token=? ORDER BY updated_at DESC LIMIT 1",
            (owner_token,),
        ).fetchone()
        return dict(row) if row else None


class VersionConflict(Exception):
    def __init__(self, current: int):
        super().__init__(f"version conflict: current={current}")
        self.current = current
