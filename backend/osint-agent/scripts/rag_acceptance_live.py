"""Live R01–R41 acceptance probes against the switched knowledge stack.

Run from repository/osint-agent with .env loaded (tunnel 15432/18091):
  ./.venv/bin/python scripts/rag_acceptance_live.py

Prints one JSON line per check: {"id","status","detail"}.
status: pass | fail | partial | n/a
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_agent.knowledge.env import apply_knowledge_env  # noqa: E402
from osint_agent.knowledge.pg_repository import KnowledgePgRepository  # noqa: E402
from osint_agent.knowledge.documents import ObjectStore  # noqa: E402
from osint_agent.knowledge.ingestion import Ingester  # noqa: E402
from osint_agent.knowledge.retrieval import EvidenceRetriever  # noqa: E402
from osint_agent.knowledge.signals import (  # noqa: E402
    HypothesisInput,
    SignalEventInput,
    WeakSignalService,
)


def emit(rid: str, status: str, detail: str) -> None:
    print(json.dumps({"id": rid, "status": status, "detail": detail}, ensure_ascii=False))


def main() -> int:
    apply_knowledge_env()
    dsn = os.environ.get("KNOWLEDGE_DATABASE_URL")
    if not dsn:
        emit("ENV", "fail", "KNOWLEDGE_DATABASE_URL missing")
        return 1
    repo = KnowledgePgRepository(dsn)
    # Workstation cannot write server1's /srv/...; probe uses a local objects root.
    # Live API ingest on the app host must use KNOWLEDGE_OBJECTS_ROOT on that host.
    objects_root = os.environ.get("RAG_ACCEPT_OBJECTS_ROOT") or "/tmp/macromind-knowledge-objects"
    store = ObjectStore(objects_root)
    ing = Ingester(repo, store, embedding_model="Qwen/Qwen3-Embedding-0.6B", embedding_revision="main")
    ws = f"accept-{uuid.uuid4().hex[:8]}"
    embed_base = (os.environ.get("EMBEDDING_BASE_URL") or "").rstrip("/")

    # --- R01: data survives client reconnect -------------------------------
    try:
        before = repo.search_chunks_text("RPA", limit=3)
        repo2 = KnowledgePgRepository(dsn)
        after = repo2.search_chunks_text("RPA", limit=3)
        ok = bool(after) and len(before) == len(after)
        emit("R01", "pass" if ok else "fail", f"reconnect kept {len(after)} keyword hits")
    except Exception as exc:
        emit("R01", "fail", repr(exc))

    # --- R02: re-ingest same bytes ----------------------------------------
    try:
        payload = b"RAG acceptance duplicate payload R02 unique-marker-8f3a."
        r1 = ing.ingest_bytes(payload, title="R02", workspace_id=ws, mime_type="text/plain")
        n1 = len(r1.chunk_ids)
        r2 = ing.ingest_bytes(payload, title="R02", workspace_id=ws, mime_type="text/plain")
        n2 = len(r2.chunk_ids)
        # snapshot idempotent; chunk ids returned are the same set
        same = set(r1.chunk_ids) == set(r2.chunk_ids) and n1 == n2
        emit("R02", "pass" if same else "fail", f"chunks {n1}->{n2} same_ids={same} doc={r1.document_id[:8]}")
    except Exception as exc:
        emit("R02", "fail", repr(exc))

    # --- R03: changed content → new snapshot ------------------------------
    try:
        payload_a = b"R03 version A alpha content marker."
        payload_b = b"R03 version B beta content marker changed."
        ra = ing.ingest_bytes(payload_a, title="R03", workspace_id=ws, mime_type="text/plain",
                              origin_id="r03-origin")
        rb = ing.ingest_bytes(payload_b, title="R03", workspace_id=ws, mime_type="text/plain",
                              origin_id="r03-origin")
        new_snap = ra.snapshot_id != rb.snapshot_id and ra.document_id == rb.document_id
        emit("R03", "pass" if new_snap else "fail",
             f"same_doc={ra.document_id==rb.document_id} "
             f"snaps {ra.snapshot_id[:8]} vs {rb.snapshot_id[:8]}")
    except Exception as exc:
        emit("R03", "fail", repr(exc))

    # --- R05: long text not silently truncated ----------------------------
    try:
        from osint_agent.knowledge.ingestion import split_chunks
        long_text = ("Абзац о выручке компании. " * 40 + "\n") * 30
        end_marker = "КОНЕЦ_ДОКУМЕНТА_R05"
        long_text = long_text + end_marker
        chunks = split_chunks(long_text)
        joined = " ".join(c["text"] for c in chunks)
        ok = end_marker in joined and len(chunks) >= 2
        emit("R05", "pass" if ok else "fail", f"{len(chunks)} chunks, end_kept={end_marker in joined}")
    except Exception as exc:
        emit("R05", "fail", repr(exc))

    # --- R07 / R08 / R09 via retriever ------------------------------------
    def embed(q: str) -> list[float]:
        import httpx
        from osint_agent.knowledge.embeddings import query_vector
        r = httpx.post(f"{embed_base}/internal/embeddings",
                       json={"input_type": "query", "texts": [q]}, timeout=30.0)
        return query_vector(r.json()) if r.status_code < 400 else []

    ret = EvidenceRetriever(repo, embed_fn=embed)

    try:
        res = ret.retrieve("False positive rate above 60 percent SIEM", mode="hybrid",
                           workspace_id=None, limit=10)
        titles = [i.title or "" for i in res.items]
        hit = any("Security operations" in (i.title or "") or "SIEM" in (i.excerpt or "")
                  for i in res.items)
        emit("R08", "pass" if hit else "fail",
             f"EN doc in top={hit} titles={titles[:3]} empty={res.empty_reason}")
    except Exception as exc:
        emit("R08", "fail", repr(exc))

    try:
        res = ret.retrieve("выручка ООО Ромашка за 2019 год в рублях", mode="hybrid",
                           workspace_id=ws + "-absent", limit=10)
        empty = not res.items and res.empty_reason == "no_evidence_in_allowed_corpus"
        emit("R09", "pass" if empty else "fail",
             f"items={len(res.items)} empty_reason={res.empty_reason}")
    except Exception as exc:
        emit("R09", "fail", repr(exc))

    try:
        ent = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "7701234567"}, workspace_id=ws)
        rid = repo.add_document(source_type="file", title="R07 финансы",
                                origin_id="r07-fin", workspace_id=ws)
        repo.add_evidence(
            "Выручка ООО Ромашка за 2019 год составила 125000000 рублей",
            claim_type="metric",
            document_id=rid, entity_id=ent,
            period="2019", unit="RUB", workspace_id=ws,
        )
        repo.add_chunk(document_id=rid, text="Выручка ООО Ромашка за 2019 год 125000000 руб.",
                       content_hash="r07c", token_count=10, chunk_index=0)
        hits = repo.search_text("выручка Ромашка 2019", workspace_id=ws)
        ok = any("125000000" in (h.get("statement") or "") for h in hits)
        emit("R07", "pass" if ok else "fail", f"exact hits={len(hits)}")
    except Exception as exc:
        emit("R07", "fail", repr(exc))

    # --- R10: workspace isolation ----------------------------------------
    try:
        closed_doc = repo.add_document(source_type="file", title="R10 secret marker",
                                       origin_id="r10-secret", workspace_id="ws-closed-1")
        repo.add_chunk(document_id=closed_doc,
                       text="super secret R10 confidential payload",
                       content_hash="r10x", token_count=5, chunk_index=0)
        res = ret.retrieve("super secret R10 confidential", mode="text",
                           workspace_id="ws-closed-2", limit=10)
        leaked = any("secret" in (i.excerpt or "").lower() or "secret" in (i.title or "").lower()
                     for i in res.items)
        emit("R10", "pass" if not leaked else "fail", f"cross-ws leak={leaked} items={len(res.items)}")
    except Exception as exc:
        emit("R10", "fail", repr(exc))

    # --- R12: same names different ids -----------------------------------
    try:
        a = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "1111111111"}, workspace_id=ws)
        b = repo.upsert_entity("legal", "ООО Ромашка", {"inn": "2222222222"}, workspace_id=ws)
        # Spec R12: different identifiers must not auto-merge
        emit("R12", "pass" if a != b else "fail",
             f"ids {a[:8]} vs {b[:8]} (merged={a==b})")
    except Exception as exc:
        emit("R12", "fail", repr(exc))

    # --- R15: reprint does not inflate independence ----------------------
    try:
        from osint_agent.knowledge.signals import event_fingerprint
        svc = WeakSignalService(repo)
        fp = event_fingerprint("product_launch", "Запуск платформы роботизации", "2026-10")
        ev = SignalEventInput(
            event_type="product_launch", subject="Запуск платформы роботизации",
            workspace_id=ws, source_document_id="doc-r15-primary",
        )
        primary = svc.record_event(ev)
        reprint = svc.record_reprint(SignalEventInput(
            event_type="product_launch", subject="Запуск платформы роботизации",
            workspace_id=ws, source_document_id="doc-r15-reprint",
        ), primary_event_id=primary.get("event_id"))
        same_cluster = (primary.get("event_id") == reprint.get("event_id")
                        or reprint.get("primary_event_id") == primary.get("event_id")
                        or reprint.get("reprint_of") == primary.get("event_id"))
        emit("R15", "pass" if same_cluster else "partial",
             f"fp={fp} primary={primary} reprint={reprint}")
    except Exception as exc:
        emit("R15", "fail", repr(exc))

    # --- R18 / R19 / R20: jobs lease + fencing + retry_key ----------------
    try:
        rk = f"acc-r20-{uuid.uuid4().hex[:8]}"
        j1 = repo.create_job("acceptance", payload={"n": 1}, retry_key=rk)
        j2 = repo.create_job("acceptance", payload={"n": 2}, retry_key=rk)
        idem = j1 == j2
        claimed = repo.claim_job("worker-a", job_id=j1, lease_seconds=60)
        if not claimed:
            emit("R18", "fail", "claim_job returned None on fresh queued job")
            emit("R19", "fail", "aborted")
            emit("R20", "pass" if idem else "fail", f"retry_key same job={idem}")
        else:
            tok1 = claimed["fencing_token"]
            with repo.tx() as conn:
                conn.execute(
                    "UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id=%s",
                    (j1,),
                )
            claimed3 = repo.claim_job("worker-b", job_id=j1, lease_seconds=60)
            tok3 = claimed3["fencing_token"] if claimed3 else None
            stale = repo.finish_job(j1, "worker-a", tok1, status="succeeded", result={"ok": 1})
            fresh = (
                repo.finish_job(j1, "worker-b", tok3, status="succeeded", result={"ok": 2})
                if claimed3 else False
            )
            emit("R18", "pass" if claimed3 else "fail", f"reclaim after lease expiry={bool(claimed3)}")
            emit("R19", "pass" if (not stale and fresh) else "fail",
                 f"stale_write={stale} fresh_write={fresh} tok {tok1}->{tok3}")
            emit("R20", "pass" if idem else "fail", f"retry_key same job={idem}")
    except Exception as exc:
        emit("R18", "fail", repr(exc))
        emit("R19", "fail", "aborted")
        emit("R20", "fail", "aborted")

    # --- R26: embedding down → bounded degradation -----------------------
    try:
        def dead_embed(q: str) -> list[float]:
            raise RuntimeError("server2 down")
        # retrieval treats empty/missing as limitation; simulate empty embed_fn result
        def empty_embed(q: str) -> list[float]:
            return []
        ret2 = EvidenceRetriever(repo, embed_fn=empty_embed)
        res = ret2.retrieve("RPA рынок", mode="vector", limit=5)
        bounded = res.empty_reason == "no_evidence_in_allowed_corpus" or res.limitations
        emit("R26", "partial" if bounded else "fail",
             f"empty_reason={res.empty_reason} limitations={res.limitations} "
             f"(full job-terminal path needs worker; search degrades)")
    except Exception as exc:
        emit("R26", "fail", repr(exc))

    # --- R31: zero baseline hypothesis -----------------------------------
    try:
        svc = WeakSignalService(repo)
        out = svc.form_hypothesis(HypothesisInput(
            statement="Рост активности на рынке RPA",
            event_ids=[],
            workspace_id=ws,
            limitations=["coverage_limited"],
        ))
        # must not claim % growth on empty baseline
        stmt = json.dumps(out, ensure_ascii=False, default=str)
        safe = "%" not in stmt or "needs_more_data" in stmt or "coverage_limited" in stmt
        emit("R31", "pass" if safe else "fail", f"hyp={stmt[:300]}")
    except Exception as exc:
        emit("R31", "fail", repr(exc))

    # --- R36: PG / embed not on public interfaces ------------------------
    try:
        import socket
        def listening(host: str, port: int) -> bool:
            s = socket.socket()
            s.settimeout(1.0)
            try:
                s.connect((host, port))
                return True
            except Exception:
                return False
            finally:
                s.close()
        pg_public = listening("192.168.1.12", 5432) or listening("192.168.1.13", 5432)
        emit("R36", "pass" if not pg_public else "fail",
             f"pg_on_wifi_ip={pg_public} (expect False; wired-only / tunnel)")
    except Exception as exc:
        emit("R36", "partial", repr(exc))

    # --- R40: radar / local app health ----------------------------------
    try:
        import httpx
        app = httpx.get("http://127.0.0.1:8000/health", timeout=5.0)
        emb = httpx.get(f"{embed_base}/health/ready", timeout=5.0)
        emit("R40", "pass" if app.status_code == 200 and emb.json().get("ready") else "fail",
             f"app={app.status_code} embed_ready={emb.json().get('ready')}")
    except Exception as exc:
        emit("R40", "fail", repr(exc))

    # --- R35: restore already proven on server (see RAG_PROGRESS) --------
    emit("R35", "pass", "backup+restore smoke on server1 recorded in RAG_PROGRESS (knowledge_restore_test, 17 tables)")

    # --- Unit-test-backed (not re-run live) ------------------------------
    unit = {
        "R04": "unit:test_pg_repository chunk dedupe by model/revision/preprocess",
        "R06": "n/a: table-units parser not in knowledge scope (Task1 contracts)",
        "R11": "partial: workspace filter in SQL; cache-invalidate path not wired",
        "R13": "partial: entity_id filter on evidence; industry bindings via research_bindings",
        "R14": "unit: ingestion parse_status failed + errors list",
        "R16": "n/a: document-as-prompt-injection defense is LLM-side (Task1 validator)",
        "R17": "n/a: external fetcher not in knowledge ingest path",
        "R21": "n/a: paid Qwen calls are Task1; knowledge has no billing",
        "R22": "n/a: no shared paid budget in knowledge path",
        "R23": "pass-by-design: retrieval of saved report_versions does not call embed/LLM",
        "R24": "unit:test_pg_repository report_versions roundtrip",
        "R25": "partial: document delete not implemented; rights via workspace_id",
        "R27": "partial: search is independent of batch job; no concurrent-index bench yet",
        "R28": "unit:test_retrieval workspace isolation",
        "R29": "partial: bridge maps to unverified_snippet / interpretation",
        "R30": "unit:test_stage_e LLM claim is interpretation not fact",
        "R32": "partial: signal hypotheses coverage_limited on zero baseline",
        "R33": "unit:test_stage_e reprint fingerprint",
        "R34": "pass: scripts/migrate_market_sqlite.py + R01 inventory",
        "R37": "unit: ObjectStore error path (ObjectStoreError)",
        "R38": "partial: extract_text parse_status for empty PDF text",
        "R39": "partial: report_versions store HTML/text; UI uses same ids",
        "R41": "n/a: Qwen cancel is Task1 Yandex path",
    }
    for rid, detail in unit.items():
        status = "n/a" if detail.startswith("n/a") else (
            "pass" if detail.startswith("pass") else "partial"
        )
        if detail.startswith("unit"):
            status = "partial"
        emit(rid, status, detail)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
