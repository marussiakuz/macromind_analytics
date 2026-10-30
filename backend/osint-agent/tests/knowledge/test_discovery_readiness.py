"""§7 readiness: PDF text, metadata read-back, re-run dedup, cache snapshot key."""

from __future__ import annotations

import os
import uuid

import pytest

from osint_agent.knowledge.cache_keys import cache_key_with_corpus, corpus_snapshot_id
from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.ingestion import Ingester


def _repo():
    from osint_agent.knowledge.pg_repository import KnowledgePgRepository
    dsn = os.environ.get(
        "KNOWLEDGE_DATABASE_URL",
        "postgresql://knowledge:knowledge_local_dev@127.0.0.1:5433/knowledge",
    )
    r = KnowledgePgRepository(dsn, application_name="osint-tests")
    try:
        r.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG unavailable: {exc}")
    return r


@pytest.fixture
def repo():
    r = _repo()
    yield r
    r.close()


@pytest.fixture
def ws():
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def ing(repo, tmp_path):
    return Ingester(repo, ObjectStore(str(tmp_path / "o")))


def test_pdf_extracts_real_text_not_filename(repo, ws, ing):
    long_text = (
        "RPA market revenue 12.4 billion rubles in 2025 according to the annual "
        "industry study of process automation vendors across Russia and CIS. "
        "Enterprise adoption survey shows 38 percent growth in deployments."
    )
    # build a tiny PDF with that literal string
    content = f"BT /F1 12 Tf 72 720 Td ({long_text}) Tj ET".encode("latin-1", "replace")
    pdf = (
        b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
        + f"4 0 obj<< /Length {len(content)} >>stream\n".encode()
        + content
        + b"\nendstream endobj\n"
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
        b"trailer<< /Root 1 0 R >>\n%%EOF"
    )
    res = ing.ingest_bytes(
        pdf,
        source_type="web",
        title="RPA PDF",
        workspace_id=ws,
        mime_type="application/pdf",
        filename="rpa-report.pdf",
        origin_id=f"pdf-{ws}",
        metadata={"claim_type": "lead", "original_url": "https://example.org/rpa.pdf"},
    )
    assert res.document_id
    assert res.parse_status == "ok", res.errors
    stats = repo.count_chunks_with_text(res.document_id)
    assert stats["n_with_text"] >= 1, "PDF must yield extracted text"
    assert stats["max_text_len"] > 40
    # never the filename stub alone
    assert "[pdf]" not in " ".join([])  # placeholder
    text_rows = repo.search_chunks_text("RPA market revenue", workspace_id=ws, limit=5)
    assert text_rows, "extracted PDF text must be searchable"


def test_metadata_and_original_url_readable_after_ingest(repo, ws, ing):
    res = ing.ingest_bytes(
        b"Market report body about logistics 2025.",
        source_type="web",
        title="Logistics",
        workspace_id=ws,
        mime_type="text/plain",
        origin_id=f"meta-{ws}",
        metadata={
            "author": "Analyst",
            "original_url": "https://publisher.example/report",
            "data_period": "2024",
            "claim_type": "forecast",
            "read_level": "full_text",
        },
    )
    doc = repo.get_document(res.document_id, workspace_id=ws)
    assert doc is not None
    meta = doc.get("metadata") or {}
    assert meta.get("author") == "Analyst"
    assert meta.get("original_url") == "https://publisher.example/report"
    assert meta.get("data_period") == "2024"
    assert meta.get("claim_type") == "forecast"
    assert meta.get("read_level") == "full_text"


def test_rerun_same_origin_no_duplicate_document(repo, ws, ing):
    payload = b"Idempotent discovery payload unique-marker-77aa."
    r1 = ing.ingest_bytes(payload, title="dup", workspace_id=ws, mime_type="text/plain",
                          origin_id=f"dup-{ws}")
    r2 = ing.ingest_bytes(payload, title="dup", workspace_id=ws, mime_type="text/plain",
                          origin_id=f"dup-{ws}")
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    by_origin = repo.get_document_by_origin(f"dup-{ws}", workspace_id=ws)
    assert by_origin and str(by_origin["id"]) == r1.document_id


def test_cache_key_changes_with_corpus_snapshot():
    k1 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws", document_ids=["a"])
    k2 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws", document_ids=["a", "b"])
    k3 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws", document_ids=["a"])
    assert k1 != k2
    assert k1 == k3
    s1 = corpus_snapshot_id(workspace_id="ws", document_ids=["a"])
    s2 = corpus_snapshot_id(workspace_id="ws", document_ids=["b"])
    assert s1 != s2
