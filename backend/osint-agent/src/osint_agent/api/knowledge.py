"""Knowledge API (Task2 §12). Access is checked in SQL; empty search is normal."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from osint_agent.knowledge.access import Principal, current_principal
from osint_agent.knowledge.bridge import KnowledgeBridge
from osint_agent.knowledge.documents import ObjectStore
from osint_agent.knowledge.env import apply_knowledge_env, knowledge_dsn
from osint_agent.knowledge.ingestion import Ingester
from osint_agent.knowledge.pg_repository import KnowledgePgRepository
from osint_agent.knowledge.retrieval import EvidenceRetriever
from osint_agent.knowledge.signals import (
    HypothesisInput,
    SignalEventInput,
    WeakSignalService,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

_repo: KnowledgePgRepository | None = None
_store: ObjectStore | None = None


def get_repo() -> KnowledgePgRepository:
    global _repo
    if _repo is None:
        apply_knowledge_env()
        dsn = knowledge_dsn()
        if not dsn:
            raise HTTPException(503, detail="KNOWLEDGE_DATABASE_URL is not configured")
        _repo = KnowledgePgRepository(dsn)
    return _repo


def get_store() -> ObjectStore:
    global _store
    if _store is None:
        apply_knowledge_env()
        root = os.environ.get("KNOWLEDGE_OBJECTS_ROOT", "data/knowledge-objects")
        _store = ObjectStore(root)
    return _store


def set_repo(repo: KnowledgePgRepository | None) -> None:
    global _repo
    _repo = repo


def _ws(principal: Principal, requested: str | None) -> str | None:
    return principal.workspace_filter(requested)


class IngestIn(BaseModel):
    text: str | None = None
    url: str | None = None
    title: str | None = None
    source_type: str = "file"
    mime_type: str = "text/plain"
    origin_id: str | None = None
    workspace_id: str | None = None


class SearchIn(BaseModel):
    question: str
    mode: Literal["exact", "text", "vector", "hybrid"] = "hybrid"
    workspace_id: str | None = None
    entity_id: str | None = None
    source_types: list[str] | None = None
    since: date | None = None
    embedding_model: str | None = None
    embedding_revision: str | None = None
    limit: int = Field(default=12, ge=1, le=50)


class EventIn(BaseModel):
    event_type: str
    subject: str
    technology: str | None = None
    company: str | None = None
    geography: str | None = None
    event_at: date | None = None
    published_at: date | None = None
    source_document_id: str | None = None
    source_evidence_id: str | None = None
    notes: str | None = None
    workspace_id: str | None = None
    watchlist_id: str | None = None
    is_reprint: bool = False
    primary_event_id: str | None = None


class WatchlistIn(BaseModel):
    topic: str
    products: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    schedule_cron: str | None = None
    workspace_id: str | None = None


class HypothesisIn(BaseModel):
    statement: str
    event_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None
    workspace_id: str | None = None
    watchlist_id: str | None = None


class BridgeIn(BaseModel):
    summary: dict[str, Any]
    workspace_id: str | None = None
    inn: str | None = None


@router.post("/ingestions")
async def ingest(body: IngestIn, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not body.text:
        raise HTTPException(400, detail="text is required in this version")
    ws = _ws(principal, body.workspace_id)
    ing = Ingester(get_repo(), get_store())
    res = ing.ingest_bytes(
        body.text.encode("utf-8"),
        source_type=body.source_type,
        url=body.url,
        title=body.title,
        origin_id=body.origin_id,
        mime_type=body.mime_type,
        workspace_id=ws,
    )
    status_row = get_repo().get_document_index_status(res.document_id) if res.document_id else None
    return {
        "document_id": res.document_id,
        "snapshot_id": res.snapshot_id,
        "chunk_ids": res.chunk_ids,
        "job_ids": res.job_ids,
        "parse_status": res.parse_status,
        "index_status": (status_row or {}).get("index_status") or ("saved" if res.document_id else None),
        "errors": res.errors,
        "workspace_id": ws,
    }


@router.post("/search")
async def search(body: SearchIn, principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    embed_fn = None
    apply_knowledge_env()
    base = os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
    ws = _ws(principal, body.workspace_id)

    def _embed(q: str) -> list[float]:
        import httpx

        from osint_agent.knowledge.embeddings import query_vector

        r = httpx.post(
            f"{base}/internal/embeddings",
            json={"input_type": "query", "texts": [q]},
            timeout=30.0,
        )
        if r.status_code >= 400:
            return []
        return query_vector(r.json())

    if body.mode in ("vector", "hybrid"):
        embed_fn = _embed

    ret = EvidenceRetriever(get_repo(), embed_fn=embed_fn)
    res = ret.retrieve(
        body.question,
        mode=body.mode,
        workspace_id=ws,
        entity_id=body.entity_id,
        source_types=body.source_types,
        since=body.since,
        embedding_model=body.embedding_model,
        embedding_revision=body.embedding_revision,
        limit=body.limit,
    )
    return {
        "retrieval_id": res.retrieval_id,
        "mode": res.mode,
        "items": [
            {
                "evidence_id": i.evidence_id,
                "chunk_id": i.chunk_id,
                "snapshot_id": i.snapshot_id,
                "document_id": i.document_id,
                "title": i.title,
                "source_url": i.source_url,
                "locator": i.locator,
                "excerpt": i.excerpt,
                "published_at": i.published_at,
                "retrieved_at": i.retrieved_at,
                "verification_status": i.verification_status,
                "score": i.score,
                "rank": i.rank,
                "origin": i.origin,
                "source": i.source,
                "read_level": i.read_level,
            }
            for i in res.items
        ],
        "limitations": res.limitations,
        "empty_reason": res.empty_reason,
    }


@router.get("/evidence/{evidence_id}")
async def get_evidence(
    evidence_id: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    """Fetch by id + allowed workspaces. Foreign id → 404 (no existence leak)."""
    if principal.is_service or principal.allowed_workspaces is None:
        allowed = None
    else:
        allowed = sorted(principal.allowed_workspaces)
    row = get_repo().get_evidence_by_id(evidence_id, allowed_workspaces=allowed)
    if not row:
        raise HTTPException(404, detail="evidence not found")
    return dict(row)


@router.post("/bridge/market")
async def bridge_market(
    body: BridgeIn,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    ws = _ws(principal, body.workspace_id)
    br = KnowledgeBridge(get_repo())
    return br.persist_market_evidence(body.summary, workspace_id=ws, inn=body.inn)


@router.post("/watchlists")
async def create_watchlist(
    body: WatchlistIn,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    ws = _ws(principal, body.workspace_id)
    svc = WeakSignalService(get_repo())
    wid = svc.save_watchlist(
        body.topic,
        products=body.products,
        technologies=body.technologies,
        companies=body.companies,
        queries=body.queries,
        geography=body.geography,
        schedule_cron=body.schedule_cron,
        workspace_id=ws,
    )
    return {"id": wid, "workspace_id": ws}


@router.post("/signals/events")
async def record_event(
    body: EventIn,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    ws = _ws(principal, body.workspace_id)
    svc = WeakSignalService(get_repo())
    inp = SignalEventInput(
        event_type=body.event_type,
        subject=body.subject,
        technology=body.technology,
        company=body.company,
        geography=body.geography,
        event_at=body.event_at,
        published_at=body.published_at,
        source_document_id=body.source_document_id,
        source_evidence_id=body.source_evidence_id,
        notes=body.notes,
        workspace_id=ws,
        watchlist_id=body.watchlist_id,
    )
    if body.is_reprint:
        return svc.record_reprint(inp, primary_event_id=body.primary_event_id)
    return svc.record_event(inp)


@router.get("/signals")
async def list_signals(
    workspace_id: str | None = None,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    ws = _ws(principal, workspace_id)
    svc = WeakSignalService(get_repo())
    return {
        "events": svc.list_events(workspace_id=ws),
        "hypotheses": svc.list_hypotheses(workspace_id=ws),
    }


@router.post("/signals/hypotheses")
async def create_hypothesis(
    body: HypothesisIn,
    principal: Principal = Depends(current_principal),
) -> dict[str, Any]:
    ws = _ws(principal, body.workspace_id)
    svc = WeakSignalService(get_repo())
    return svc.form_hypothesis(
        HypothesisInput(
            statement=body.statement,
            event_ids=body.event_ids,
            evidence_ids=body.evidence_ids,
            limitations=body.limitations,
            alternatives=body.alternatives,
            questions=body.questions,
            window_start=body.window_start,
            window_end=body.window_end,
            baseline_start=body.baseline_start,
            baseline_end=body.baseline_end,
            workspace_id=ws,
            watchlist_id=body.watchlist_id,
        )
    )
