#!/usr/bin/env python3
"""Tune min_similarity for vector retrieval on the labeled bench set."""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DSN = "postgresql://knowledge:knowledge_local_dev@127.0.0.1:15432/knowledge"
EMB = "http://127.0.0.1:18091"


def emb(texts: list[str], t: str = "query") -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 8):
        b = texts[i : i + 8]
        r = httpx.post(f"{EMB}/internal/embeddings", json={"input_type": t, "texts": b}, timeout=60)
        out.extend(r.json()["vectors"])
    return out


def cos(a, b):
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1
    nb = math.sqrt(sum(x * x for x in b)) or 1
    return s / (na * nb)


def main() -> None:
    data = json.loads((ROOT / "tests/knowledge/data/recall_bench_v1.json").read_text())
    conn = psycopg.connect(DSN, row_factory=psycopg.rows.dict_row)
    rows = conn.execute(
        """
        select d.workspace_id, d.id as doc_id, c.embedding
        from chunks c join documents d on d.id=c.document_id
        where d.workspace_id like 'bench-recall-%' and c.embedding is not null
        """
    ).fetchall()
    by_ws = defaultdict(list)
    for r in rows:
        by_ws[r["workspace_id"]].append(r)
    ws = sorted(by_ws, key=lambda w: -len(by_ws[w]))[0]
    chunks = by_ws[ws]
    print(f"workspace={ws} chunks={len(chunks)}")

    doc_ids = {r["doc_id"] for r in chunks}
    # map bench doc id -> db doc id via origin_id
    origins = {
        r["origin_id"]: r["id"]
        for r in conn.execute(
            "select origin_id, id from documents where workspace_id=%s",
            (ws,),
        ).fetchall()
    }
    bench_to_db = {}
    for doc in data["documents"]:
        oid = f"bench-{doc['id']}"
        if oid in origins:
            bench_to_db[doc["id"]] = origins[oid]
    print(f"mapped {len(bench_to_db)} bench docs")
    db_to_bench = {v: k for k, v in bench_to_db.items()}

    vecs = []
    for r in chunks:
        e = r["embedding"]
        if isinstance(e, str):
            e = json.loads(e)
        vecs.append((db_to_bench.get(r["doc_id"], r["doc_id"]), e))

    pos_rel = []
    un_max = []
    for q in data["questions"]:
        if q.get("split") != "dev":
            continue  # Never tune a threshold on held-out control questions.
        qv = emb([q["text"]])[0]
        sims = sorted(((cos(qv, v), d) for d, v in vecs), reverse=True)
        if q.get("answerable"):
            rel_ids = set(q.get("relevant") or [])
            rel_sims = [s for s, d in sims if d in rel_ids]
            pos_rel.append((q["id"], max(rel_sims) if rel_sims else None, sims[0][0], q.get("category")))
        else:
            un_max.append((q["id"], sims[0][0], [round(s, 3) for s, _ in sims[:3]]))

    rel_vals = [x[1] for x in pos_rel if x[1] is not None]
    un_vals = [x[1] for x in un_max]
    print("\nANSWERABLE max-sim to relevant doc: min/med/max")
    print(min(rel_vals), sorted(rel_vals)[len(rel_vals) // 2], max(rel_vals))
    print("low end (potential misses):")
    for x in sorted(pos_rel, key=lambda t: t[1] if t[1] is not None else -1)[:10]:
        print(x)
    print("\nUNANSWERABLE max-sim to any doc:")
    for x in sorted(un_max, key=lambda t: -t[1]):
        print(x)
    print("unans max/med/min", max(un_vals), sorted(un_vals)[len(un_vals) // 2], min(un_vals))

    print("\nThreshold sweep (min_similarity):")
    for thr in [x / 100 for x in range(5, 75, 5)]:
        tp = sum(1 for v in rel_vals if v >= thr)
        fp = sum(1 for v in un_vals if v >= thr)
        print(f"  thr={thr:.2f}  pos_kept={tp}/{len(rel_vals)}  unans_flagged={fp}/{len(un_vals)}")
    conn.close()


if __name__ == "__main__":
    main()
