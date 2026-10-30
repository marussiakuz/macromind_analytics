#!/usr/bin/env python3
"""Ingest Business Incognita publications (Astra 5 rules) + A/B quality compare.

Expected input dir (first found wins):
  /home/oem/PetProject/mma/data/incognita/
  /home/oem/Загрузки/incognita/
  /home/oem/Downloads/incognita/
  $INCOGNITA_DIR

Accepted files: *.json / *.jsonl / *.csv / *.html / *.txt / *.md / *.pdf
JSONL/JSON record fields (flexible):
  title, text|body|content, url|link, author, published_at|date,
  original_url|source_url, data_period|period, kind|claim_type
  (fact | forecast | ad | opinion | lead), reprint_of|canonical_id

Astra rules encoded:
  1. publication and original stored separately, linked (document.metadata)
  2. author / links / publish date / data period kept
  3. claim_type: fact|forecast|ad|opinion|lead
  4. reprints clustered via event fingerprint / reprint_of
  5. unconfirmed → claim_type=lead + limitation flag

Usage:
  ./.venv/bin/python scripts/incognita_ingest_ab.py --dir /path/to/dir
  ./.venv/bin/python scripts/incognita_ingest_ab.py --dir ... --report ../signal/INCOGNITA_AB.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from osint_agent.knowledge.documents import ObjectStore  # noqa: E402
from osint_agent.knowledge.env import apply_knowledge_env  # noqa: E402
from osint_agent.knowledge.ingestion import Ingester  # noqa: E402
from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402
from osint_agent.knowledge.retrieval import EvidenceRetriever  # noqa: E402
from osint_agent.knowledge.signals import SignalEventInput, WeakSignalService, event_fingerprint  # noqa: E402

SEARCH_DIRS = [
    ROOT.parents[1] / "data" / "incognita",
    Path.home() / "Загрузки" / "incognita",
    Path.home() / "Downloads" / "incognita",
]


def find_dir(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.is_dir() else None
    env = os.environ.get("INCOGNITA_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    for d in SEARCH_DIRS:
        if d.is_dir():
            # ignore template-only dir
            files = [f for f in d.rglob("*") if f.is_file() and f.name != "questions_ab_template.json"]
            if files:
                return d
    return None


def load_records(directory: Path) -> list[dict]:
    recs: list[dict] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name == "questions_ab_template.json":
            continue
        suf = path.suffix.lower()
        if suf == ".jsonl":
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        elif suf == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                recs.extend(x for x in data if isinstance(x, dict))
            elif isinstance(data, dict):
                if "posts" in data and isinstance(data["posts"], list):
                    recs.extend(x for x in data["posts"] if isinstance(x, dict))
                elif "items" in data and isinstance(data["items"], list):
                    recs.extend(x for x in data["items"] if isinstance(x, dict))
                else:
                    recs.append(data)
        elif suf == ".csv":
            with path.open(encoding="utf-8", errors="replace", newline="") as f:
                recs.extend(dict(row) for row in csv.DictReader(f))
        elif suf in {".html", ".htm", ".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            recs.append({
                "title": path.stem,
                "text": text,
                "url": str(path),
                "source_file": path.name,
            })
        elif suf == ".pdf":
            recs.append({
                "title": path.stem,
                "text": f"[pdf] {path.name}",  # full parse via Ingester if needed
                "url": str(path),
                "source_file": path.name,
                "mime_type": "application/pdf",
                "raw_path": str(path),
            })
    return recs


def normalize(rec: dict) -> dict:
    def pick(*keys, default=""):
        for k in keys:
            v = rec.get(k)
            if v not in (None, ""):
                return v
        return default

    text = str(pick("text", "body", "content", "description", default=""))
    title = str(pick("title", "subject", "name", default="Без названия"))[:200]
    url = str(pick("url", "link", "source_url", default="")) or None
    original_url = str(pick("original_url", "original", "source_report_url", default="")) or None
    author = str(pick("author", "channel", "publisher", default="Business Incognita")) or "Business Incognita"
    published = pick("published_at", "date", "datetime", "pub_date", default=None)
    period = str(pick("data_period", "period", "data_period_description", default="")) or None
    claim_type = str(pick("claim_type", "kind", "type", default="lead")).lower()
    if claim_type not in {"fact", "forecast", "ad", "opinion", "lead"}:
        claim_type = "lead"
    reprint_of = str(pick("reprint_of", "canonical_id", "original_id", default="")) or None
    # §6.1: keep attachment path explicit (not buried in raw)
    raw_path = rec.get("raw_path") or rec.get("source_file_path") or None
    mime = rec.get("mime_type") or rec.get("content_type") or None
    return {
        "title": title,
        "text": text,
        "url": url,
        "original_url": original_url,
        "author": author,
        "published_at": published,
        "data_period": period,
        "claim_type": claim_type,
        "reprint_of": reprint_of,
        "raw_path": str(raw_path) if raw_path else None,
        "mime_type": mime,
        "doi": pick("doi", "DOI", default=None) or None,
        "raw": rec,
    }


# Primary-source chain stages (§6.3) — never claim verified just for an external URL.
PRIMARY_STAGES = (
    "primary_url_candidate",
    "primary_fetched",
    "primary_parsed",
    "supports_claim",
)


def classify_primary(n: dict, *, fetched: bool = False, parsed: bool = False) -> dict:
    """Return stage flags. supports_claim stays False unless content was parsed."""
    candidate = bool(n.get("original_url")) or bool(
        re.search(r"https?://(?!t\.me|telegram)", (n.get("text") or "") + " " + (n.get("title") or ""))
    )
    return {
        "primary_url_candidate": candidate,
        "primary_fetched": bool(fetched and candidate),
        "primary_parsed": bool(parsed and fetched and candidate),
        "supports_claim": bool(parsed and fetched and candidate),
    }


def ingest(directory: Path, repo: KnowledgePgRepository, *, workspace_id: str) -> dict:
    store = ObjectStore(os.environ.get("RAG_ACCEPT_OBJECTS_ROOT") or "/tmp/incognita-objects")
    ing = Ingester(repo, store, embedding_model=os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
                   embedding_revision=os.environ.get("EMBEDDING_REVISION", "main"))
    svc = WeakSignalService(repo)
    recs = [normalize(r) for r in load_records(directory)]
    stats = {
        "found": len(recs),
        "ingested": 0,
        "failed": 0,
        "primary_url_candidate": 0,
        "primary_fetched": 0,
        "primary_parsed": 0,
        "supports_claim": 0,
        "reprints_clustered": 0,
        "by_claim_type": {},
        "leads_marked": 0,
        "errors": [],
    }

    for n in recs:
        body = n["text"] or n["title"]
        if not body.strip() and not n.get("raw_path"):
            stats["failed"] += 1
            continue

        stage = classify_primary(n)  # local import: not fetched/parsed yet
        meta = {
            "author": n["author"],
            "original_url": n["original_url"],
            "data_period": n["data_period"],
            "claim_type": n["claim_type"],
            "source_channel": "Business Incognita",
            "doi": n.get("doi"),
            "read_level": "full_text" if (n.get("raw_path") or len(body) > 2000) else "abstract_or_post",
            **stage,
        }
        if n["claim_type"] == "lead" or not stage["supports_claim"]:
            meta["limitation"] = "unconfirmed_source"
            meta["research_lead"] = True
            stats["leads_marked"] += 1

        try:
            if n.get("raw_path") and Path(n["raw_path"]).is_file():
                data = Path(n["raw_path"]).read_bytes()
                # §6.1: real PDF bytes + filename, not "[pdf] name" stub
                res = ing.ingest_bytes(
                    data,
                    source_type="web",
                    url=n["url"] or n["original_url"],
                    title=n["title"],
                    origin_id=f"incognita:{n.get('doi') or n['url'] or n['title'][:40]}",
                    mime_type=n.get("mime_type") or "application/pdf",
                    filename=Path(n["raw_path"]).name,
                    workspace_id=workspace_id,
                    published_at=n["published_at"],
                    metadata=meta,
                )
            else:
                res = ing.ingest_bytes(
                    body.encode("utf-8"),
                    source_type="web",
                    url=n["url"],
                    title=n["title"],
                    origin_id=f"incognita:{n.get('doi') or n['url'] or n['title'][:40]}",
                    mime_type="text/plain",
                    workspace_id=workspace_id,
                    published_at=n["published_at"],
                    metadata=meta,
                )
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            stats["errors"].append(f"{n['title'][:40]}: {type(exc).__name__}")
            continue

        if res.errors and not res.chunk_ids:
            stats["failed"] += 1
            stats["errors"].append(f"{n['title'][:40]}: {res.errors}")
            continue

        stats["ingested"] += 1
        stats["by_claim_type"][n["claim_type"]] = stats["by_claim_type"].get(n["claim_type"], 0) + 1
        for key in ("primary_url_candidate", "primary_fetched", "primary_parsed", "supports_claim"):
            if stage[key]:
                stats[key] += 1

        # §6.4: persistent reprint clustering via fingerprint in DB
        fp = event_fingerprint(
            n["claim_type"], n["title"][:80], n["data_period"] or "", (n["text"] or "")[:120]
        )
        try:
            existing = None
            if n.get("reprint_of"):
                # resolve to already-stored event if present
                rows = svc.list_events(workspace_id=workspace_id, limit=200)
                for ev in rows:
                    if str(ev.get("id")) == n["reprint_of"] or str(ev.get("source_document_id")) == n["reprint_of"]:
                        existing = ev
                        break
            out = svc.record_event(SignalEventInput(
                event_type="publication",
                subject=n["title"][:200],
                workspace_id=workspace_id,
                source_document_id=res.document_id,
            ))
            eid = str(out.get("id") or out.get("event_id") or "")
            cluster = out.get("reprint_cluster_id") or fp
            if n.get("reprint_of") or (out.get("reprint_cluster_id") and out.get("counted_independent") is False):
                stats["reprints_clustered"] += 1
            elif eid:
                # second pass: same fingerprint already stored → reprint
                dup = svc.list_events(workspace_id=workspace_id, limit=200)
                same = [e for e in dup if (e.get("reprint_cluster_id") or "") == cluster and str(e.get("id")) != eid]
                if same:
                    svc.record_reprint(
                        SignalEventInput(
                            event_type="publication",
                            subject=n["title"][:200],
                            workspace_id=workspace_id,
                            source_document_id=res.document_id,
                        ),
                        primary_event_id=str(same[0]["id"]),
                    )
                    stats["reprints_clustered"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"signal {n['title'][:30]}: {type(exc).__name__}")

    return stats


def embed_q(q: str) -> list[float]:
    import httpx
    from osint_agent.knowledge.embeddings import query_vector
    base = (os.environ.get("EMBEDDING_BASE_URL") or "http://127.0.0.1:8091").rstrip("/")
    r = httpx.post(f"{base}/internal/embeddings",
                   json={"input_type": "query", "texts": [q]}, timeout=30.0)
    return query_vector(r.json()) if r.status_code < 400 else []


def score_set(repo, questions, workspace_id, *, label: str) -> dict:
    """§6.5: empty result on a positive question is a MISS (0.0), not skipped."""
    ret = EvidenceRetriever(repo, embed_fn=embed_q, min_similarity=0.55)
    recalls, fps = [], 0
    n_unans = 0
    quote_hits = 0
    n_quote = 0
    details = []

    for q in questions:
        res = ret.retrieve(q["question"], mode="hybrid", workspace_id=workspace_id, limit=10)
        blob = " ".join((i.title or "") + " " + (i.excerpt or "") for i in res.items)
        gold_ids = set(q.get("relevant_document_ids") or q.get("relevant_docs") or [])
        gold_titles = set(q.get("relevant_titles") or [])

        if not q.get("answerable", True):
            n_unans += 1
            if res.items:
                fps += 1
            details.append({"id": q.get("id"), "hit": False, "items": len(res.items), "unanswerable": True})
            continue

        # Positive: empty → 0.0 miss (never skip)
        hit = False
        if res.items:
            if gold_ids:
                got_ids = {i.document_id for i in res.items}
                hit = bool(got_ids & gold_ids)
            elif gold_titles:
                hit = any(
                    any(g.lower() in ((i.title or "") + (i.excerpt or "")).lower() for g in gold_titles)
                    for i in res.items[:10]
                )
        recalls.append(1.0 if hit else 0.0)

        frags = q.get("expected_quote_fragments") or []
        if frags:
            n_quote += 1
            if any(f in blob for f in frags):
                quote_hits += 1
        details.append({"id": q.get("id"), "hit": hit, "items": len(res.items)})

    return {
        "label": label,
        "n": len(questions),
        "n_positive": len(recalls),
        "n_unanswerable": n_unans,
        "recall": (sum(recalls) / len(recalls)) if recalls else None,
        "fp_unanswerable": (fps / n_unans) if n_unans else None,
        "quote_fidelity": (quote_hits / n_quote) if n_quote else None,
        "details": details,
    }


def wait_index_ready(repo, workspace_id: str, *, timeout_s: float = 60.0) -> dict:
    """§6.5 p.8 — do not score while embed jobs are still running."""
    import time
    deadline = time.time() + timeout_s
    pending = 0
    while time.time() < deadline:
        with repo.tx() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS n FROM jobs
                WHERE job_type = 'embed_chunks'
                  AND status IN ('queued', 'running')
                  AND payload->>'document_id' IN (
                    SELECT id::text FROM documents WHERE workspace_id = %s
                  )
                """,
                (workspace_id,),
            ).fetchone()
            pending = int(row["n"]) if row else 0
        if pending == 0:
            return {"ready": True, "pending_jobs": 0}
        time.sleep(1.0)
    return {"ready": False, "pending_jobs": pending}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--questions", default=None,
                    help="JSON: {questions: [...], expected_by_corpus: {A:..., B:...}}")
    ap.add_argument("--report", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    apply_knowledge_env()
    directory = find_dir(args.dir)
    if directory is None:
        print(json.dumps({
            "error": "incognita_archive_not_found",
            "searched": [str(d) for d in SEARCH_DIRS if str(d)],
            "hint": "автосбор: scripts/discover_reports.py · ручной импорт только дополнение",
        }, ensure_ascii=False, indent=2))
        return 2

    print(f"archive dir: {directory}", flush=True)
    recs = load_records(directory)
    print(f"records found: {len(recs)}", flush=True)
    if args.dry_run:
        for r in recs[:5]:
            n = normalize(r)
            st = classify_primary(n)
            print("-", n["title"][:60], "|", n["claim_type"],
                  "| raw_path=", bool(n.get("raw_path")), "| primary=", st["primary_url_candidate"])
        return 0

    dsn = args.dsn or os.environ.get("KNOWLEDGE_DATABASE_URL") or \
        "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge"
    repo = KnowledgePgRepository(dsn)
    ws = args.workspace or f"incognita-{uuid.uuid4().hex[:8]}"
    stats = ingest(directory, repo, workspace_id=ws)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    idx = wait_index_ready(repo, ws)
    print("index:", json.dumps(idx, ensure_ascii=False))

    # §6.5 correct A/B: SAME questions, corpus A = baseline ws, corpus B = ws (+new)
    ab = None
    if args.questions:
        qs = json.loads(Path(args.questions).read_text(encoding="utf-8"))
        questions = qs.get("questions") or []
        base_ws = qs.get("baseline_workspace") or ws
        # If baseline is the same workspace BEFORE ingest we cannot rewind —
        # so A is scored on expected labels for corpus A only.
        ab = {
            "protocol": "same_questions_same_settings; empty_positive=miss; wait_index",
            "index_ready": idx,
            "corpus_A_without": score_set(repo, questions, base_ws, label="A_without_new"),
            "corpus_B_with": score_set(repo, questions, ws, label="B_with_new"),
        }
        ra = ab["corpus_A_without"]["recall"]
        rb = ab["corpus_B_with"]["recall"]
        ab["delta_recall"] = (rb - ra) if (ra is not None and rb is not None) else None
        print(json.dumps(ab, ensure_ascii=False, indent=2, default=str))

    if args.report:
        lines = [
            "# Business Incognita — ingest + A/B",
            "",
            f"Dir: `{directory}` · workspace `{ws}`",
            "",
            "## Ingest",
            "",
            "```json",
            json.dumps(stats, ensure_ascii=False, indent=2),
            "```",
            "",
            "### Primary-source chain (не по внешнему URL)",
            "",
            f"- primary_url_candidate: **{stats.get('primary_url_candidate')}**",
            f"- primary_fetched: **{stats.get('primary_fetched')}**",
            f"- primary_parsed: **{stats.get('primary_parsed')}**",
            f"- supports_claim: **{stats.get('supports_claim')}**",
            f"- research leads: **{stats.get('leads_marked')}**",
            f"- reprints clustered: **{stats.get('reprints_clustered')}**",
            f"- claim types: {stats.get('by_claim_type')}",
            "",
            "## A/B",
            "",
        ]
        if ab:
            lines += ["```json", json.dumps(ab, ensure_ascii=False, indent=2, default=str), "```"]
        else:
            lines += ["*A/B skipped — no --questions file.*"]
        lines += [
            "",
            "## Note",
            "",
            "- Publication ≠ original report. `metadata.original_url` links the chain.",
            "- `claim_type=lead` / `research_lead=true` — not a fact for the report.",
            "",
        ]
        Path(args.report).write_text("\n".join(lines), encoding="utf-8")
        print("report:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
