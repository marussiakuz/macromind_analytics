"""Evidence retrieval: exact / text / vector + RRF hybrid (Task2 RAG §8).

Exact SQL for facts; keyword + semantic for texts; RRF merge;
access filter in SQL (not after generation); empty result with reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from osint_agent.knowledge.pg_repository import KnowledgePgRepository

RRF_K = 60
CANDIDATES_PER_SOURCE = 30
SELECTED_MAX = 12
SELECTED_MIN = 8


@dataclass
class RetrievalItem:
    evidence_id: str | None
    chunk_id: str | None
    snapshot_id: str | None
    document_id: str | None
    title: str | None
    source_url: str | None
    excerpt: str
    locator: dict[str, Any] | None
    published_at: str | None
    retrieved_at: str | None
    verification_status: str
    score: float
    rank: int
    origin: str  # exact | text | vector
    source: str | None = None  # openalex | yandex | registry | file | ...
    read_level: str | None = None  # abstract_only | full_text | html_or_text | snippet_only


@dataclass
class RetrievalResult:
    retrieval_id: str | None
    mode: str
    items: list[RetrievalItem] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    empty_reason: str | None = None


class EvidenceRetriever:
    def __init__(
        self,
        repo: KnowledgePgRepository,
        *,
        embed_fn: Callable[[str], list[float]] | None = None,
        rrf_k: int = RRF_K,
        selected_max: int = SELECTED_MAX,
        min_similarity: float = 0.55,
    ):
        self.repo = repo
        self.embed_fn = embed_fn
        self.rrf_k = rrf_k
        self.selected_max = selected_max
        # Tuned on quality_holdout_v1 split=dev (NOT holdout): 0.55 clears
        # unanswerable FPs while keeping recall 1.0 on dev. Holdout scored once
        # with this frozen value — see signal/RAG_QUALITY_HOLDOUT.md.
        self.min_similarity = min_similarity

    def retrieve(
        self,
        question: str,
        *,
        mode: str = "hybrid",
        workspace_id: str | None = None,
        entity_id: str | None = None,
        source_types: list[str] | None = None,
        since=None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
        limit: int | None = None,
    ) -> RetrievalResult:
        limitations: list[str] = []
        filters = {
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "source_types": source_types,
            "since": str(since) if since else None,
            "embedding_model": embedding_model,
            "embedding_revision": embedding_revision,
        }

        # 1) exact facts via SQL (for numeric/company questions — R07)
        exact: list[RetrievalItem] = []
        if mode in ("exact", "hybrid"):
            exact = self._exact_facts(
                question,
                workspace_id=workspace_id,
                entity_id=entity_id,
                source_types=source_types,
                since=since,
            )

        # 2) keyword candidates — filters applied in SQL before LIMIT
        text_hits: list[RetrievalItem] = []
        if mode in ("text", "hybrid"):
            text_hits = self._text_candidates(
                question,
                workspace_id=workspace_id,
                source_types=source_types,
                since=since,
                entity_id=entity_id,
                embedding_model=embedding_model,
                embedding_revision=embedding_revision,
                limit=CANDIDATES_PER_SOURCE,
            )

        # 3) vector candidates — same filters in SQL; never mix model profiles
        vec_hits: list[RetrievalItem] = []
        if mode in ("vector", "hybrid"):
            if self.embed_fn is None:
                limitations.append("embedding_service_unavailable")
            else:
                try:
                    vec_hits = self._vector_candidates(
                        question,
                        workspace_id=workspace_id,
                        source_types=source_types,
                        since=since,
                        entity_id=entity_id,
                        embedding_model=embedding_model,
                        embedding_revision=embedding_revision,
                        limit=CANDIDATES_PER_SOURCE,
                    )
                except httpx.HTTPError:
                    limitations.append("embedding_service_unavailable")
                else:
                    if not vec_hits:
                        limitations.append("vector_empty")

        merged = self._rrf_merge(exact, text_hits, vec_hits)
        merged = self._dedupe_by_document(merged, max_per_doc=3)
        selected = merged[: (limit or self.selected_max)]

        if not selected:
            return RetrievalResult(
                retrieval_id=None,
                mode=mode,
                items=[],
                limitations=limitations,
                empty_reason="no_evidence_in_allowed_corpus",
            )
        if len(selected) < SELECTED_MIN:
            limitations.append(f"few_candidates:{len(selected)}")

        rid = self.repo.save_retrieval_run(
            question=question,
            mode=mode,
            filters=filters,
            candidates=[
                {"chunk_id": i.chunk_id, "evidence_id": i.evidence_id, "score": i.score, "origin": i.origin}
                for i in merged[:CANDIDATES_PER_SOURCE]
            ],
            selected=[
                {"chunk_id": i.chunk_id, "evidence_id": i.evidence_id, "score": i.score, "rank": i.rank}
                for i in selected
            ],
            scores={"rrf_k": self.rrf_k},
            limitations=limitations,
            workspace_id=workspace_id,
        )
        for i, item in enumerate(selected):
            item.rank = i + 1
        return RetrievalResult(retrieval_id=rid, mode=mode, items=selected, limitations=limitations)

    # --- sources -----------------------------------------------------------

    def _exact_facts(
        self,
        question: str,
        *,
        workspace_id: str | None,
        entity_id: str | None,
        source_types: list[str] | None = None,
        since=None,
    ) -> list[RetrievalItem]:
        rows = self.repo.search_text(
            question,
            limit=CANDIDATES_PER_SOURCE,
            workspace_id=workspace_id,
            entity_id=entity_id,
            source_types=source_types,
            since=since,
        )
        out: list[RetrievalItem] = []
        for r in rows:
            out.append(self._row_to_item(r, origin="exact", score=1.0))
        return out

    def _text_candidates(
        self,
        question: str,
        *,
        workspace_id: str | None,
        source_types: list[str] | None,
        limit: int,
        since=None,
        entity_id: str | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
    ) -> list[RetrievalItem]:
        rows = self.repo.search_chunks_text(
            question,
            limit=limit,
            workspace_id=workspace_id,
            source_types=source_types,
            since=since,
            entity_id=entity_id,
            embedding_model=embedding_model,
            embedding_revision=embedding_revision,
        )
        return [self._row_to_item(r, origin="text", score=0.5) for r in rows]

    def _vector_candidates(
        self,
        question: str,
        *,
        workspace_id: str | None,
        source_types: list[str] | None,
        limit: int,
        since=None,
        entity_id: str | None = None,
        embedding_model: str | None = None,
        embedding_revision: str | None = None,
    ) -> list[RetrievalItem]:
        if self.embed_fn is None:
            return []
        qvec = self.embed_fn(question)
        if not qvec:
            return []
        rows = self.repo.vector_search(
            qvec,
            limit=limit,
            workspace_id=workspace_id,
            min_similarity=self.min_similarity,
            source_types=source_types,
            since=since,
            entity_id=entity_id,
            embedding_model=embedding_model,
            embedding_revision=embedding_revision,
        )
        out: list[RetrievalItem] = []
        for r in rows:
            score = float(r.get("sim") or 0.0)
            out.append(self._row_to_item(r, origin="vector", score=score))
        return out

    def _row_to_item(self, r: dict, *, origin: str, score: float) -> RetrievalItem:
        meta = r.get("metadata") or {}
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta)
            except Exception:
                meta = {}
        read_level = (
            r.get("read_level")
            or (meta.get("read_level") if isinstance(meta, dict) else None)
            or "unknown"
        )
        source = (
            r.get("source")
            or (meta.get("source") if isinstance(meta, dict) else None)
            or r.get("source_type")
        )
        return RetrievalItem(
            evidence_id=str(r["id"]) if r.get("id") and origin == "exact" else (
                str(r["evidence_id"]) if r.get("evidence_id") else None
            ),
            chunk_id=str(r["chunk_id"]) if r.get("chunk_id") else None,
            snapshot_id=str(r["snapshot_id"]) if r.get("snapshot_id") else None,
            document_id=str(r["document_id"]) if r.get("document_id") else None,
            title=r.get("title") or r.get("statement"),
            source_url=r.get("url"),
            excerpt=r.get("excerpt") or r.get("quote") or r.get("statement") or r.get("text") or "",
            locator=r.get("locator"),
            published_at=str(r["published_at"]) if r.get("published_at") else None,
            retrieved_at=str(r["retrieved_at"]) if r.get("retrieved_at") else None,
            verification_status=r.get("verification_status") or "unreviewed",
            score=score,
            rank=0,
            origin=origin,
            source=source,
            read_level=read_level,
        )

    def _rrf_merge(self, *lists: list[RetrievalItem]) -> list[RetrievalItem]:
        scores: dict[str, float] = {}
        best: dict[str, RetrievalItem] = {}
        for lst in lists:
            for rank, item in enumerate(lst, start=1):
                key = item.chunk_id or item.evidence_id or item.excerpt[:64]
                scores[key] = scores.get(key, 0.0) + 1.0 / (self.rrf_k + rank)
                prev = best.get(key)
                if prev is None or item.score > prev.score:
                    best[key] = item
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        out: list[RetrievalItem] = []
        for key, sc in ordered:
            it = best[key]
            out.append(RetrievalItem(
                evidence_id=it.evidence_id,
                chunk_id=it.chunk_id,
                snapshot_id=it.snapshot_id,
                document_id=it.document_id,
                title=it.title,
                source_url=it.source_url,
                excerpt=it.excerpt,
                locator=it.locator,
                published_at=it.published_at,
                retrieved_at=it.retrieved_at,
                verification_status=it.verification_status,
                score=sc,
                rank=0,
                origin=it.origin,
                source=it.source,
                read_level=it.read_level,
            ))
        return out

    def _dedupe_by_document(self, items: list[RetrievalItem], *, max_per_doc: int = 3) -> list[RetrievalItem]:
        counts: dict[str, int] = {}
        out: list[RetrievalItem] = []
        for it in items:
            doc = it.document_id or it.source_url or "?"
            if counts.get(doc, 0) >= max_per_doc:
                continue
            counts[doc] = counts.get(doc, 0) + 1
            out.append(it)
        return out
