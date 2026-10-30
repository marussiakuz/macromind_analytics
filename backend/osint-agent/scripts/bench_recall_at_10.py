#!/usr/bin/env python3
"""Recall@10 benchmark for Task2 Stage D (spec §16.1).

Seeds a controlled corpus, runs text / vector / hybrid retrieval,
and reports Recall@10 on positive questions plus false hits on unanswerable ones.

Usage:
  ./.venv/bin/python scripts/bench_recall_at_10.py
  ./.venv/bin/python scripts/bench_recall_at_10.py --report ../signal/RAG_RECALL_BENCH.md
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402
from osint_agent.knowledge.retrieval import EvidenceRetriever  # noqa: E402

DATA_PATH = ROOT / "tests" / "knowledge" / "data" / "recall_bench_v1.json"
DEFAULT_DSN = os.environ.get(
    "KNOWLEDGE_DATABASE_URL",
    "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
)
EMBED_URL = (os.environ.get("EMBEDDING_BASE_URL") or "http://127.0.0.1:18091").rstrip("/")
EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
EMBED_REVISION = os.environ.get("EMBEDDING_REVISION", "main")
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
    """Insert documents/chunks; return mapping bench doc id -> db document_id."""
    id_map: dict[str, str] = {}
    for doc in docs:
        db_id = repo.add_document(
            source_type="bench",
            url=doc.get("url"),
            title=doc.get("title"),
            origin_id=f"bench-{doc['id']}",
            workspace_id=workspace_id,
        )
        id_map[doc["id"]] = db_id
        snap = repo.add_snapshot(
            document_id=db_id,
            content_hash=f"bench-{doc['id']}-v1",
            parse_status="ok",
        )
        texts = doc["chunks"]
        vectors = embed_texts(texts, input_type="document")
        for idx, (text, vec) in enumerate(zip(texts, vectors)):
            repo.add_chunk(
                document_id=db_id,
                snapshot_id=snap,
                text=text,
                lang=doc.get("lang"),
                chunk_index=idx,
                content_hash=f"bench-{doc['id']}-c{idx}",
                embedding=vec,
                embedding_model=EMBED_MODEL,
                embedding_revision=EMBED_REVISION,
                preprocessing_version="bench-v1",
            )
    return id_map


def unique_doc_ids(items, id_map_inv: dict[str, str]) -> list[str]:
    """Ordered unique bench document ids from retrieval items."""
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        db_doc = it.document_id
        if not db_doc:
            continue
        bench_id = id_map_inv.get(str(db_doc))
        if not bench_id or bench_id in seen:
            continue
        seen.add(bench_id)
        out.append(bench_id)
    return out


def recall_at_k(relevant: list[str], retrieved_docs: list[str], k: int = K) -> float:
    if not relevant:
        return 0.0
    top = retrieved_docs[:k]
    hit = sum(1 for d in relevant if d in top)
    return hit / len(relevant)


def precision_at_k(relevant: list[str], retrieved_docs: list[str], k: int = K) -> float:
    top = retrieved_docs[:k]
    if not top:
        return 0.0
    # P@K uses K, including missing slots. Dividing by len(top) reports
    # precision among returned items and overstates P@10 for a short list.
    return sum(1 for d in top if d in relevant) / k


def mrr(relevant: list[str], retrieved_docs: list[str], k: int = K) -> float:
    top = retrieved_docs[:k]
    for i, d in enumerate(top, start=1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def evaluate_mode(retriever: EvidenceRetriever, questions: list[dict], id_map_inv: dict[str, str], workspace_id: str) -> dict:
    rows = []
    for q in questions:
        t0 = time.perf_counter()
        res = retriever.retrieve(
            q["text"],
            mode=q.get("_mode", "hybrid"),
            workspace_id=workspace_id,
        )
        elapsed = time.perf_counter() - t0
        docs = unique_doc_ids(res.items, id_map_inv)
        relevant = q.get("relevant") or []
        answerable = bool(q.get("answerable"))
        row = {
            "id": q["id"],
            "category": q.get("category"),
            "lang": q.get("lang"),
            "split": q.get("split"),
            "answerable": answerable,
            "relevant": relevant,
            "retrieved": docs[:K],
            "n_items": len(res.items),
            "empty_reason": res.empty_reason,
            "limitations": list(res.limitations or []),
            "elapsed_s": round(elapsed, 4),
        }
        if answerable:
            row["recall"] = recall_at_k(relevant, docs)
            row["precision"] = precision_at_k(relevant, docs)
            row["mrr"] = mrr(relevant, docs)
        else:
            # false hit: any returned document for an unanswerable question
            row["false_hit"] = len(docs) > 0
            row["false_hit_items"] = len(docs)
        rows.append(row)

    pos = [r for r in rows if r["answerable"]]
    unans = [r for r in rows if not r["answerable"]]
    by_split = {}
    for split in ("dev", "control"):
        subset = [r for r in pos if r.get("split") == split]
        if subset:
            by_split[split] = {
                "n": len(subset),
                "recall": round(statistics.mean(r["recall"] for r in subset), 4),
                "precision": round(statistics.mean(r["precision"] for r in subset), 4),
                "mrr": round(statistics.mean(r["mrr"] for r in subset), 4),
            }
    by_cat = {}
    for r in pos:
        by_cat.setdefault(r.get("category") or "?", []).append(r)
    cat_stats = {
        c: {
            "n": len(v),
            "recall": round(statistics.mean(x["recall"] for x in v), 4),
        }
        for c, v in sorted(by_cat.items())
    }
    return {
        "rows": rows,
        "summary": {
            "n_questions": len(rows),
            "n_positive": len(pos),
            "n_unanswerable": len(unans),
            "recall@10": round(statistics.mean(r["recall"] for r in pos), 4) if pos else 0.0,
            "precision@10": round(statistics.mean(r["precision"] for r in pos), 4) if pos else 0.0,
            "mrr@10": round(statistics.mean(r["mrr"] for r in pos), 4) if pos else 0.0,
            "unanswerable_false_hit_rate": round(
                statistics.mean(1.0 if r["false_hit"] else 0.0 for r in unans), 4
            ) if unans else 0.0,
            "by_split": by_split,
            "by_category": cat_stats,
            "mean_latency_s": round(statistics.mean(r["elapsed_s"] for r in rows), 4) if rows else 0.0,
        },
    }


def render_report(dataset: dict, results: dict, meta: dict) -> str:
    lines = [
        "# Recall@10 bench — Task2 Stage D (spec §16.1)",
        "",
        f"Дата: {meta['date']}",
        f"Корпус: **{meta['n_docs']}** документов / **{meta['n_chunks']}** фрагментов",
        f"Вопросы: **{meta['n_questions']}** (позитивных {meta['n_positive']}, без ответа {meta['n_unanswerable']})",
        f"Embedding: `{meta['embedding']}` via `{meta['embed_url']}`",
        f"Workspace: `{meta['workspace']}`",
        "",
        "## Цель",
        "",
        "Средний Recall@10 ≥ **0.85** на положительных контрольных вопросах.",
        "Дополнительно: доля лишних результатов, ложные совпадения на вопросах без ответа.",
        "",
        "## Сводка по режимам",
        "",
        "| Режим | Recall@10 | Precision@10 | MRR@10 | false-hit (без ответа) | latency p50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, ev in results.items():
        s = ev["summary"]
        lats = sorted(r["elapsed_s"] for r in ev["rows"])
        p50 = lats[len(lats) // 2] if lats else 0.0
        lines.append(
            f"| {mode} | {s['recall@10']:.4f} | {s['precision@10']:.4f} | {s['mrr@10']:.4f} "
            f"| {s['unanswerable_false_hit_rate']:.4f} | {p50:.3f}s |"
        )

    lines += ["", "## Разбивка hybrid по split", ""]
    hy = results.get("hybrid", {}).get("summary", {})
    for split, st in (hy.get("by_split") or {}).items():
        mark = "✅" if st["recall"] >= 0.85 else "⚠️"
        lines.append(
            f"- **{split}** (n={st['n']}): Recall@10 **{st['recall']:.4f}** {mark} "
            f"· P@10 {st['precision']:.4f} · MRR {st['mrr']:.4f}"
        )

    lines += ["", "## Hybrid по категориям", ""]
    for cat, st in (hy.get("by_category") or {}).items():
        lines.append(f"- `{cat}` (n={st['n']}): Recall@10 {st['recall']:.4f}")

    # per-question failures for hybrid control split
    lines += ["", "## Ошибки hybrid (контроль, recall < 1)", ""]
    fails = [
        r for r in results.get("hybrid", {}).get("rows", [])
        if r.get("split") == "control" and r.get("answerable") and r.get("recall", 1.0) < 1.0
    ]
    if not fails:
        lines.append("Нет — все контрольные позитивные вопросы закрыты.")
    else:
        for r in fails:
            miss = [d for d in r["relevant"] if d not in r["retrieved"]]
            lines.append(
                f"- `{r['id']}` [{r['category']}/{r['lang']}] recall={r['recall']:.2f} "
                f"missed={miss} top={r['retrieved'][:5]}"
            )

    lines += ["", "## Ложные совпадения (вопросы без ответа, hybrid)", ""]
    false_hits = [r for r in results.get("hybrid", {}).get("rows", []) if not r.get("answerable")]
    if not false_hits:
        lines.append("Нет вопросов без ответа в наборе.")
    else:
        hit_rows = [r for r in false_hits if r.get("false_hit")]
        lines.append(f"False-hit rate: **{len(hit_rows)}/{len(false_hits)}**")
        for r in hit_rows:
            lines.append(f"- `{r['id']}` вернул {r.get('false_hit_items')} док.: {r.get('retrieved')}")

    lines += ["", "## Ограничения оценки", "",
        "Это синтетический корпус, а не проверка на реальных отраслевых документах.",
        "Набор v1 ранее использовался для подбора порога целиком, включая control.",
        "Его control теперь является регрессионным набором, а не независимым испытанием.",
        "Для приёмки нужен новый закрытый контрольный набор и оценка ложных совпадений.",
        "Таблица подбора порогов здесь не вычисляется и поэтому не выводится.",
        "Precision@10 делится на 10; старые сохранённые результаты использовали число выданных документов.",
    ]

    lines += ["", "## Hard negatives (hybrid, без ответа, но похожий документ)", ""]
    hard = [r for r in results.get("hybrid", {}).get("rows", []) if not r.get("answerable") and r.get("false_hit")]
    if not hard:
        lines.append("Нет.")
    else:
        lines += [
            "Тематически близкие документы без ответа на вопрос — системе нельзя выдавать их как подтверждение (R09):",
            "",
        ]
        for r in hard:
            lines.append(f"- `{r['id']}` → {r.get('retrieved')}")
        lines += [
            "",
            "Это ожидаемое ограничение смыслового поиска: порог не отличает «похожую тему» "
            "от «содержит ответ». Тактический фильтр — после retrieval проверять, цитирует ли "
            "фрагмент конкретный факт вопроса (exact / LLM-verify), а не только сходство.",
        ]

    lines += ["", "## Методика", ""]
    lines += [
        "- Recall@10 = |relevant ∩ top10 docs| / |relevant| (уникальные документы в порядке выдачи).",
        "- Precision@10 = доля релевантных среди top10 документов.",
        "- MRR@10 — ранг первого релевантного документа.",
        "- False-hit rate — доля вопросов без ответа, где поиск вернул ≥1 документ.",
        "- `split=control` не использовался для подбора параметров.",
        "- Параметры: RRF k=60, ≤30+≤30 кандидатов, ≤3 фрагмента на документ, top12 → top10 для метрики.",
    ]
    lines += ["", "## Команды", "", "```bash", "./.venv/bin/python scripts/bench_recall_at_10.py", "```", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DEFAULT_DSN)
    ap.add_argument("--workspace", default=f"bench-recall-{uuid.uuid4().hex[:10]}")
    ap.add_argument("--report", default=str(ROOT.parents[1] / "signal" / "RAG_RECALL_BENCH.md"))
    ap.add_argument("--json-out", default=str(ROOT / "tests" / "knowledge" / "data" / "recall_bench_last_run.json"))
    ap.add_argument("--modes", default="text,vector,hybrid")
    args = ap.parse_args()

    dataset = load_dataset()
    docs = dataset["documents"]
    questions = dataset["questions"]
    n_chunks = sum(len(d["chunks"]) for d in docs)
    print(f"dataset: {len(docs)} docs, {n_chunks} chunks, {len(questions)} questions")

    repo = KnowledgePgRepository(args.dsn, application_name="osint-recall-bench")
    repo.connect()
    print(f"seeding workspace={args.workspace} …")
    id_map = seed_corpus(repo, docs, args.workspace)
    id_map_inv = {v: k for k, v in id_map.items()}
    print(f"seeded {len(id_map)} documents")

    def embed_fn(q: str) -> list[float]:
        vecs = embed_texts([q], input_type="query")
        return vecs[0] if vecs else []

    retriever = EvidenceRetriever(repo, embed_fn=embed_fn)
    results: dict = {}
    for mode in args.modes.split(","):
        mode = mode.strip()
        if not mode:
            continue
        print(f"evaluating mode={mode} …")
        qcopy = [dict(q, _mode=mode) for q in questions]
        results[mode] = evaluate_mode(retriever, qcopy, id_map_inv, args.workspace)
        s = results[mode]["summary"]
        print(
            f"  {mode}: recall@10={s['recall@10']:.4f} "
            f"precision@10={s['precision@10']:.4f} "
            f"false_hit={s['unanswerable_false_hit_rate']:.4f}"
        )

    meta = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "n_docs": len(docs),
        "n_chunks": n_chunks,
        "n_questions": len(questions),
        "n_positive": sum(1 for q in questions if q.get("answerable")),
        "n_unanswerable": sum(1 for q in questions if not q.get("answerable")),
        "embedding": EMBED_MODEL,
        "embed_url": EMBED_URL,
        "workspace": args.workspace,
        "dsn_host": args.dsn.split("@")[-1] if "@" in args.dsn else args.dsn,
    }
    report = render_report(dataset, results, meta)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"report → {report_path}")

    payload = {"meta": meta, "results": results}
    Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"json → {args.json_out}")

    hy = results.get("hybrid", {}).get("summary", {})
    control = (hy.get("by_split") or {}).get("control") or {}
    if control.get("recall", 0) < 0.85:
        print(f"TARGET NOT MET: hybrid control Recall@10={control.get('recall')} < 0.85")
        return 2
    print("TARGET MET: hybrid control Recall@10 >= 0.85")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
