#!/usr/bin/env python3
"""Discovery scheduler CLI (server 1). Budget + interval from env.

  ./.venv/bin/python scripts/discovery_scheduler.py --once --product "RPA"
  ./.venv/bin/python scripts/discovery_scheduler.py --product "RPA" --geo "Россия"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_agent.knowledge.discovery.queries import ProductProfile  # noqa: E402
from osint_agent.knowledge.discovery.scheduler import scheduler_from_env  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--geo", default="Россия")
    ap.add_argument("--buyers", default=None)
    ap.add_argument("--workspace", default="discovery")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=None, help="override seconds")
    args = ap.parse_args()

    profile = ProductProfile(
        product=args.product,
        geography=args.geo,
        buyers=args.buyers,
        year_from=2024,
        year_to=2026,
    )
    sched = scheduler_from_env([profile], workspace_id=args.workspace)
    if args.once:
        out = asyncio.run(sched.run_once())
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        print(json.dumps(sched.ui_status(), ensure_ascii=False, indent=2, default=str))
        return 0
    print(json.dumps(sched.ui_status(), ensure_ascii=False, indent=2, default=str))
    asyncio.run(sched.serve(interval_s=args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
