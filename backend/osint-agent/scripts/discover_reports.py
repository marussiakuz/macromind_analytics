#!/usr/bin/env python3
"""CLI: automatic report discovery (Yandex publishers + OpenAlex).

  ./.venv/bin/python scripts/discover_reports.py --product "RPA" --geo "Россия"
  ./.venv/bin/python scripts/discover_reports.py --from-summary data/summary.json --report ../signal/DISCOVERY_RUN.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_agent.knowledge.discovery.pipeline import discover_and_ingest  # noqa: E402
from osint_agent.knowledge.discovery.queries import ProductProfile  # noqa: E402
from osint_agent.knowledge.env import apply_knowledge_env  # noqa: E402
from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default=None)
    ap.add_argument("--geo", default="Россия")
    ap.add_argument("--buyers", default=None)
    ap.add_argument("--year-from", type=int, default=2024)
    ap.add_argument("--year-to", type=int, default=2026)
    ap.add_argument("--from-summary", default=None, help="JSON auto-analysis summary")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--no-fetch", action="store_true", help="store search leads only")
    ap.add_argument("--dry-run", action="store_true", help="print queries only")
    args = ap.parse_args()

    if args.from_summary:
        summary = json.loads(Path(args.from_summary).read_text(encoding="utf-8"))
        profile = ProductProfile.from_analysis(summary)
    elif args.product:
        profile = ProductProfile(
            product=args.product,
            geography=args.geo,
            buyers=args.buyers,
            year_from=args.year_from,
            year_to=args.year_to,
        )
    else:
        print(json.dumps({"error": "need --product or --from-summary"}))
        return 2

    from osint_agent.knowledge.discovery.queries import build_queries, openalex_search_terms
    queries = build_queries(profile)
    terms = openalex_search_terms(profile)
    if args.dry_run:
        print(json.dumps({"queries": queries, "openalex_terms": terms}, ensure_ascii=False, indent=2))
        return 0

    apply_knowledge_env()
    dsn = args.dsn or os.environ.get("KNOWLEDGE_DATABASE_URL") or \
        "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge"
    repo = KnowledgePgRepository(dsn)
    ws = args.workspace or f"discovery-{uuid.uuid4().hex[:8]}"

    result = asyncio.run(discover_and_ingest(
        profile, repo, workspace_id=ws, fetch_externals=not args.no_fetch,
    ))
    payload = {
        "workspace": ws,
        "product": profile.product,
        "queries": result.queries,
        "yandex_hits": len(result.yandex_hits),
        "openalex_works": [
            {"doi": w.doi, "title": w.title[:80], "read_level": w.read_level,
             "full_text_url": w.full_text_url, "date": w.publication_date,
             "authors": w.authors[:5]}
            for w in result.openalex_works
        ],
        "fetched": result.fetched,
        "ingested": result.ingested,
        "failed": result.failed,
        "by_source": result.by_source,
        "limitations": result.limitations,
        "details": result.details[:30],
        "note": "cited_by_count is not market growth evidence",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    if args.report:
        Path(args.report).write_text(
            "# Discovery run\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            + "\n```\n",
            encoding="utf-8",
        )
        print("report:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
