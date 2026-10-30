#!/usr/bin/env python3
"""Migrate Task1 SQLite market data → knowledge PostgreSQL (R34).

Usage:
  python scripts/migrate_market_sqlite.py \
      --sqlite data/market.db \
      --dsn postgresql://knowledge:***@127.0.0.1:5433/knowledge

Preserves version numbers and summary JSON. Reports source as 'imported'
where origin cannot be confirmed (spec §6.1).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402


def migrate(sqlite_path: str, dsn: str, *, dry_run: bool = False) -> dict:
    if not Path(sqlite_path).is_file():
        return {"error": f"sqlite not found: {sqlite_path}", "migrated": 0}
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    tables = {
        r["name"]
        for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    stats = {"analysis_versions": 0, "research_jobs": 0, "skipped": 0, "dry_run": dry_run}

    if "analysis_versions" not in tables:
        src.close()
        return {**stats, "note": "no analysis_versions table"}

    rows = src.execute(
        """
        SELECT id, study_id, legal_entity_inn, version, status, summary_json, request_key, created_at
        FROM analysis_versions
        ORDER BY version
        """
    ).fetchall()
    src.close()

    if dry_run:
        stats["analysis_versions"] = len(rows)
        return stats

    repo = KnowledgePgRepository(dsn, application_name="market-sqlite-migrate")
    try:
        for row in rows:
            summary = row["summary_json"]
            if isinstance(summary, str):
                summary = json.loads(summary)
            # mark limited provenance (§6.1 / §14)
            if isinstance(summary, dict):
                summary = {**summary, "_imported_from": "market.sqlite", "_provenance": "imported"}
            repo.save_analysis_version(
                version=int(row["version"]),
                status=row["status"] or "unknown",
                summary=summary,
                legal_entity_inn=row["legal_entity_inn"],
                study_id=row["study_id"],
                request_key=row["request_key"],
            )
            stats["analysis_versions"] += 1
    finally:
        repo.close()
    return stats


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sqlite", default="data/market.db")
    p.add_argument("--dsn", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    out = migrate(args.sqlite, args.dsn, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
