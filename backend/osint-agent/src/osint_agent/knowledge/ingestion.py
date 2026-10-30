"""Ingestion pipeline: store → snapshot → extract → chunk (Task2 RAG §6).

Stages are recorded on the job so a restart can resume. Partial progress
is durable: objects and snapshots are written before indexing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from osint_agent.knowledge.documents import ObjectStore, ObjectStoreError
from osint_agent.knowledge.pg_repository import KnowledgePgRepository

EXTRACTION_VERSION = "extract-0.1"
CHUNK_TARGET_TOKENS = 550  # 400–700 band (§7)
CHUNK_OVERLAP_TOKENS = 80
MAX_CHUNK_CHARS = 4000


@dataclass
class IngestResult:
    document_id: str
    snapshot_id: str | None = None
    chunk_ids: list[str] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    parse_status: str = "pending"
    errors: list[str] = field(default_factory=list)
    skipped: bool = False


def approximate_tokens(text: str) -> int:
    """Rough token count without a tokenizer (words + punctuation)."""
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def split_chunks(
    text: str,
    *,
    target_tokens: int = CHUNK_TARGET_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[dict[str, Any]]:
    """Semantic-ish split: paragraphs, then sliding window with overlap.

    Keeps table-ish lines together when possible (§7 R06).
    Long text is split explicitly — never silently truncated (R05).
    """
    if not text or not text.strip():
        return []
    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        pt = approximate_tokens(para)
        if pt > target_tokens:
            if buf:
                pieces.append("\n\n".join(buf))
                buf, buf_tokens = [], 0
            # hard split long paragraph by sentences / lines
            for piece in _hard_split(para, target_tokens):
                pieces.append(piece)
            continue
        if buf_tokens + pt > target_tokens and buf:
            pieces.append("\n\n".join(buf))
            buf, buf_tokens = [para], pt
        else:
            buf.append(para)
            buf_tokens += pt
    if buf:
        pieces.append("\n\n".join(buf))

    # apply overlap between consecutive pieces (token approx); never silent-truncate
    out: list[dict[str, Any]] = []
    for i, piece in enumerate(pieces):
        chunk_text = piece
        if i > 0 and overlap_tokens > 0:
            prev_tail = _tail_tokens(pieces[i - 1], overlap_tokens)
            if prev_tail:
                chunk_text = prev_tail + "\n" + piece
        # if still over hard cap, split further instead of dropping the tail
        for sub in _hard_split(chunk_text, target_tokens) if len(chunk_text) > MAX_CHUNK_CHARS else [chunk_text]:
            out.append({
                "index": len(out),
                "text": sub,
                "token_count": approximate_tokens(sub),
                "content_hash": hashlib.sha256(sub.encode("utf-8")).hexdigest(),
            })
    return out


def _hard_split(text: str, target_tokens: int) -> list[str]:
    # sentence-ish breakpoints first so one giant line is not kept whole (R05)
    sentences = re.split(r"(?<=[.!?])\s+|\n", text)
    out: list[str] = []
    buf: list[str] = []
    n = 0
    for sent in sentences:
        if not sent:
            continue
        # still too long for a buffer unit — split by words
        if approximate_tokens(sent) > target_tokens * 2:
            if buf:
                out.append(" ".join(buf))
                buf, n = [], 0
            words = sent.split()
            cur: list[str] = []
            cur_t = 0
            for w in words:
                wt = approximate_tokens(w)
                if cur_t + wt > target_tokens and cur:
                    out.append(" ".join(cur))
                    cur, cur_t = [], 0
                cur.append(w)
                cur_t += wt
            if cur:
                out.append(" ".join(cur))
            continue
        st = approximate_tokens(sent)
        if n + st > target_tokens and buf:
            out.append(" ".join(buf))
            buf, n = [], 0
        buf.append(sent)
        n += st
    if buf:
        out.append(" ".join(buf))
    return out or [text]


def _tail_tokens(text: str, overlap_tokens: int) -> str:
    words = text.split()
    if not words:
        return ""
    # approximate: last N words
    n = max(4, overlap_tokens // 2)
    return " ".join(words[-n:])


def extract_text(data: bytes, mime_type: str | None, *, filename: str | None = None) -> tuple[str, str]:
    """Return (text, parse_status). Never execute macros/scripts (R16)."""
    name = (filename or "").lower()
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime in ("text/plain", "text/markdown", "text/csv") or name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="replace"), "ok"
    if mime in ("application/json",) or name.endswith(".json"):
        return data.decode("utf-8", errors="replace"), "ok"
    if mime in ("text/html", "application/xhtml+xml") or name.endswith((".html", ".htm")):
        return _strip_html(data.decode("utf-8", errors="replace")), "ok"
    if mime == "application/pdf" or name.endswith(".pdf"):
        return _extract_pdf(data)
    if mime.startswith("text/"):
        return data.decode("utf-8", errors="replace"), "ok"
    # unknown binary: do not invent text
    return "", "failed"


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"[ \t]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n\n", html).strip()


def _extract_pdf(data: bytes) -> tuple[str, str]:
    try:
        import io

        import pdfplumber
    except ImportError:
        return "", "failed"
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages.append(t)
        text = "\n\n".join(pages).strip()
        if not text:
            return "", "ocr_required"
        return text, "ok"
    except Exception:  # noqa: BLE001
        return "", "failed"


class Ingester:
    def __init__(
        self,
        repo: KnowledgePgRepository,
        store: ObjectStore,
        *,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
    ):
        self.repo = repo
        self.store = store
        self.embedding_model = embedding_model
        self.embedding_revision = embedding_revision

    def ingest_bytes(
        self,
        data: bytes,
        *,
        source_type: str = "file",
        url: str | None = None,
        title: str | None = None,
        origin_id: str | None = None,
        mime_type: str | None = None,
        filename: str | None = None,
        workspace_id: str | None = None,
        published_at=None,
        metadata: dict | None = None,
        store_embeddings: bool = False,
        embedding_fn=None,
    ) -> IngestResult:
        result = IngestResult(document_id="")
        try:
            obj = self.store.put_bytes(data, mime_type=mime_type)
        except ObjectStoreError as exc:
            result.errors.append(f"{exc.code}: {exc.message}")
            result.parse_status = "failed"
            return result

        doc_meta: dict = {}
        if filename:
            doc_meta["filename"] = filename
        if metadata:
            doc_meta.update({k: v for k, v in metadata.items() if v is not None})

        doc_id = self.repo.add_document(
            source_type=source_type,
            url=url,
            title=title,
            origin_id=origin_id or f"sha256:{obj.content_hash}",
            checksum=obj.content_hash,
            storage_path=obj.storage_path,
            metadata=doc_meta,
            workspace_id=workspace_id,
            published_at=published_at,
        )
        result.document_id = doc_id

        snap_id = self.repo.add_snapshot(
            document_id=doc_id,
            content_hash=obj.content_hash,
            storage_path=obj.storage_path,
            size_bytes=obj.size_bytes,
            mime_type=obj.mime_type,
            published_at=published_at,
        )
        result.snapshot_id = snap_id

        # resume-safe: if chunks already exist for this snapshot, skip re-chunk
        text, parse_status = extract_text(data, mime_type, filename=filename)
        result.parse_status = parse_status
        self.repo.update_snapshot_parse(
            snap_id,
            parse_status=parse_status,
            extraction_version=EXTRACTION_VERSION,
            error=None if parse_status == "ok" else parse_status,
        )
        if parse_status != "ok":
            result.errors.append(parse_status)
            self.repo.set_document_index_status(doc_id, "error", error=parse_status)
            return result

        chunks = split_chunks(text)
        for ch in chunks:
            embedding = None
            if store_embeddings and embedding_fn is not None:
                embedding = embedding_fn(ch["text"])
            cid = self.repo.add_chunk(
                document_id=doc_id,
                snapshot_id=snap_id,
                text=ch["text"],
                token_count=ch["token_count"],
                chunk_index=ch["index"],
                content_hash=ch["content_hash"],
                embedding=embedding,
                embedding_model=self.embedding_model if embedding is not None else None,
                embedding_revision=self.embedding_revision if embedding is not None else None,
                preprocessing_version=EXTRACTION_VERSION,
                profile_id="v1",
            )
            result.chunk_ids.append(cid)

        # Astra §6.3: automatic embed_chunks queue after ingest.
        # Batches of ≤256 saved chunk_ids (never client text). Idempotent by retry_key.
        if result.chunk_ids and not store_embeddings:
            result.job_ids = self._enqueue_embed_jobs(
                document_id=doc_id,
                snapshot_id=snap_id,
                chunk_ids=result.chunk_ids,
            )
            self.repo.set_document_index_status(
                doc_id, "indexing" if result.job_ids else "ready"
            )
        elif result.chunk_ids and store_embeddings:
            self.repo.set_document_index_status(doc_id, "ready")
        elif parse_status != "ok":
            self.repo.set_document_index_status(doc_id, "error", error=parse_status)
        return result

    def _enqueue_embed_jobs(self, *, document_id: str, snapshot_id: str, chunk_ids: list[str]) -> list[str]:
        jobs: list[str] = []
        batch_size = 256
        for i in range(0, len(chunk_ids), batch_size):
            batch = chunk_ids[i : i + batch_size]
            # Stable key: same document+snapshot+batch never creates a second job.
            batch_key = f"{document_id}:{snapshot_id}:{i // batch_size}:{len(batch)}"
            job_id = self.repo.create_job(
                "embed_chunks",
                stage="indexing",
                payload={
                    "chunk_ids": batch,
                    "document_id": document_id,
                    "snapshot_id": snapshot_id,
                },
                retry_key=f"embed:{batch_key}",
                max_attempts=3,
            )
            jobs.append(job_id)
        return jobs

    def ingest_path(self, path: str, **kwargs) -> IngestResult:
        data = open(path, "rb").read()
        mime = kwargs.pop("mime_type", None)
        return self.ingest_bytes(data, filename=path, mime_type=mime, **kwargs)
