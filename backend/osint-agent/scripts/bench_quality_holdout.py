#!/usr/bin/env python3
"""Independent quality holdout (Astra §2 P2 / §6.4).

Evaluates retrieval quality on a CLOSED control set that was never used
for threshold tuning. Measures:
  - Recall@10 (share of relevant docs in top-10)
  - Precision@10 (hits / 10 — not hits / len(results))
  - False-positive rate on unanswerable questions
  - Quote fidelity (top result contains expected fragment)

Usage:
  ./.venv/bin/python scripts/bench_quality_holdout.py
  ./.venv/bin/python scripts/bench_quality_holdout.py --split holdout --report ../signal/RAG_QUALITY_HOLDOUT.md

Tune only on --split dev. Report holdout numbers once on a frozen config.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402
from osint_agent.knowledge.retrieval import EvidenceRetriever  # noqa: E402

DATA_PATH = ROOT / "tests" / "knowledge" / "data" / "quality_holdout_v1.json"
DEFAULT_DSN = os.environ.get(
    "KNOWLEDGE_DATABASE_URL",
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
)
EMBED_URL = (os.environ.get("EMBEDDING_BASE_URL") or "http://127.0.0.1:8091").rstrip("/")
K = 10


def load_dataset() -> dict:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def embed_texts(texts: list[str], *, input_type: str = "document") -> list[list[float]]:
    import httpx

    out: list[list[float]] = []
    for i in range(0, len(texts), 8):
        batch = texts[i : i + 8]
        r = httpx.post(
            f"{EMBED_URL}/internal/embeddings",
            json={"input_type": input_type, "texts": batch},
            timeout=60.0,
        )
        r.raise_for_status()
        vectors = r.json().get("vectors") or []
        if len(vectors) != len(batch):
            raise RuntimeError(f"embed batch mismatch: {len(vectors)} != {len(batch)}")
        out.extend(vectors)
    return out


def seed_corpus(repo: KnowledgePgRepository, docs: list[dict], workspace_id: str) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for doc in docs:
        db_id = repo.add_document(
            source_type=doc.get("source_type") or "bench",
            url=doc.get("url"),
            title=doc.get("title"),
            origin_id=f"hold-{doc['id']}",
            workspace_id=workspace_id,
            published_at=doc.get("published_at"),
        )
        id_map[doc["id"]] = db_id
        snap = repo.add_snapshot(
            document_id=db_id,
            content_hash=f"hold-{doc['id']}-v1",
            parse_status="ok",
        )
        texts = doc.get("chunks") or []
        vecs = embed_texts(texts, input_type="document") if texts else []
        for i, (text, vec) in enumerate(zip(texts, vecs)):
            repo.add_chunk(
                document_id=db_id,
                snapshot_id=snap,
                text=text,
                content_hash=f"hold-{doc['id']}-{i}",
                embedding=vec,
                embedding_model=os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
                embedding_revision=os.environ.get("EMBEDDING_REVISION", "main"),
                preprocessing_version="holdout-v1",
                chunk_index=i,
            )
    return id_map


def evaluate(
    retriever: EvidenceRetriever,
    questions: list[dict],
    id_map: dict[str, str],
    workspace_id: str,
    *,
    k: int = K,
) -> dict:
    inv = {v: k for k, v in id_map.items()}
    recalls, precisions = [], []
    unanswerable_fp = 0
    unanswerable_n = 0
    quote_hits = 0
    quote_n = 0
    details = []

    def embed_q(q: str) -> list[float]:
        return embed_texts([q], input_type="query")[0]

    retriever.embed_fn = embed_q

    for q in questions:
        res = retriever.retrieve(q["question"], mode="hybrid", workspace_id=workspace_id, limit=k)
        returned_docs = []
        for item in res.items:
            did = inv.get(item.document_id or "")
            if did:
                returned_docs.append(did)
        # unique preserve order
        seen = set()
        returned_unique = []
        for d in returned_docs:
            if d not in seen:
                seen.add(d)
                returned_unique.append(d)

        if not q.get("answerable", True):
            unanswerable_n += 1
            # any non-empty hit on unanswerable is a false positive (Astra)
            if returned_unique:
                unanswerable_fp += 1
            details.append({
                "id": q["id"], "type": "unanswerable",
                "hits": returned_unique[:3], "empty_reason": res.empty_reason,
            })
            continue

        gold = set(q.get("relevant_docs") or [])
        if gold:
            hit = gold & set(returned_unique[:k])
            recalls.append(len(hit) / len(gold))
            precisions.append(len(hit) / k)

        frags = q.get("expected_quote_fragments") or []
        if frags:
            quote_n += 1
            blob = " ".join((i.excerpt or "") + " " + (i.title or "") for i in res.items[:3])
            if any(f in blob for f in frags):
                quote_hits += 1
            details.append({
                "id": q["id"], "type": "positive",
                "returned": returned_unique[:5],
                "quote_ok": any(f in blob for f in frags),
            })
        else:
            details.append({"id": q["id"], "type": "positive", "returned": returned_unique[:5]})

    def avg(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "n_positive": len(recalls),
        "n_unanswerable": unanswerable_n,
        "recall_at_k": avg(recalls),
        "precision_at_k": avg(precisions),
        "false_positive_rate_unanswerable": (
            unanswerable_fp / unanswerable_n if unanswerable_n else None
        ),
        "quote_fidelity": (quote_hits / quote_n) if quote_n else None,
        "details": details,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="holdout", choices=["holdout", "dev", "all"])
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--k", type=int, default=K)
    args = ap.parse_args()

    data = load_dataset()
    questions = [q for q in data["questions"] if args.split == "all" or q.get("split") == args.split]
    if not questions:
        print("no questions for split", args.split)
        return 1

    repo = KnowledgePgRepository(DEFAULT_DSN)
    ws = args.workspace or f"holdout-{uuid.uuid4().hex[:8]}"
    print(f"seeding workspace={ws} docs={len(data['documents'])} …", flush=True)
    id_map = seed_corpus(repo, data["documents"], ws)

    def embed_q(q: str) -> list[float]:
        return embed_texts([q], input_type="query")[0]

    ret = EvidenceRetriever(repo, embed_fn=embed_q)
    metrics = evaluate(ret, questions, id_map, ws, k=args.k)

    targets = data.get("metrics") or {}
    print(json.dumps({k: v for k, v in metrics.items() if k != "details"}, ensure_ascii=False, indent=2))

    lines = [
        f"# Quality holdout ({args.split})",
        "",
        f"Dataset: `{DATA_PATH.name}` · workspace `{ws}` · k={args.k}",
        f"Questions: {len(questions)} (split={args.split})",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
        f"| Recall@{args.k} | {metrics['recall_at_k']} | ≥ {targets.get('recall_at_10_target', 0.85)} |",
        f"| Precision@{args.k} (hits/k) | {metrics['precision_at_k']} | — |",
        f"| False-positive rate (unanswerable) | {metrics['false_positive_rate_unanswerable']} | ≤ {targets.get('false_positive_rate_unanswerable_target_max', 0.25)} |",
        f"| Quote fidelity | {metrics['quote_fidelity']} | ≥ {targets.get('quote_fidelity_target_min', 0.8)} |",
        "",
        "## Details",
        "",
    ]
    for d in metrics["details"]:
        lines.append(f"- `{d['id']}` {d}")
    lines += [
        "",
        "## Rules",
        "",
        "- This split is for **final evaluation only** — do not tune thresholds on it.",
        "- Tune on `--split dev`, freeze config, then score holdout once.",
        "- Unanswerable hit = false positive even if the text looks related.",
        "",
    ]
    text = "\n".join(lines)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print("report:", args.report)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
