"""Automatic report discovery pipeline (MIMO_DISCOVERY §3).

Yandex (publisher sites) + OpenAlex → safe fetch → knowledge ingest.
Independent of Business Incognita.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from osint_agent.knowledge.discovery.fetch import FetchResult, fetch_document
from osint_agent.knowledge.discovery.openalex_collect import (
    WorkRecord,
    collect_openalex,
    to_knowledge_metadata,
)
from osint_agent.knowledge.discovery.provenance import classify_url, provenance_meta
from osint_agent.knowledge.discovery.queries import (
    ProductProfile,
    build_queries,
    openalex_search_terms,
)
from osint_agent.knowledge.discovery.yandex_publisher import DiscoveryHit, search_yandex


def _hit_prefix(hit: DiscoveryHit) -> str:
    """Префикс происхождения документа: exa | tavily | yandex (без суффикса _search)."""
    src = (hit.source or "").strip()
    return src.replace("_search", "") or "web"

log = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    queries: list[dict] = field(default_factory=list)
    yandex_hits: list[DiscoveryHit] = field(default_factory=list)
    openalex_works: list[WorkRecord] = field(default_factory=list)
    fetched: int = 0
    ingested: int = 0
    failed: int = 0
    skipped_paid: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


def _looks_like_pdf(fr: FetchResult) -> bool:
    ct = (fr.content_type or "").lower()
    return "pdf" in ct or (fr.data or b"")[:5] == b"%PDF-"


async def discover_and_ingest(
    profile: ProductProfile,
    repo,
    *,
    workspace_id: str,
    ingester=None,
    yandex_provider=None,
    openalex_provider=None,
    max_yandex_docs: int = 12,
    max_openalex: int = 20,
    fetch_externals: bool = True,
) -> DiscoveryResult:
    from osint_agent.knowledge.documents import ObjectStore
    from osint_agent.knowledge.ingestion import Ingester
    import os

    out = DiscoveryResult()
    out.queries = build_queries(profile)

    # --- Yandex: publisher / original reports ----------------------------
    yandex_hits: list[DiscoveryHit] = []
    if yandex_provider is not False:
        try:
            yandex_hits = await search_yandex(out.queries, provider=yandex_provider)
        except Exception as exc:  # noqa: BLE001
            out.limitations.append(f"yandex_unavailable:{type(exc).__name__}")
    out.yandex_hits = yandex_hits

    # --- OpenAlex: scholarly works with DOI/abstract --------------------
    terms = openalex_search_terms(profile)
    works: list[WorkRecord] = []
    if openalex_provider is not False:
        try:
            works = await collect_openalex(terms, provider=openalex_provider)
        except Exception as exc:  # noqa: BLE001
            out.limitations.append(f"openalex_unavailable:{type(exc).__name__}")
    out.openalex_works = works[:max_openalex]

    store = ingester
    if store is None:
        store = Ingester(
            repo,
            ObjectStore(os.environ.get("KNOWLEDGE_OBJECTS_ROOT") or "/tmp/discovery-objects"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
            embedding_revision=os.environ.get("EMBEDDING_REVISION", "main"),
        )

    # --- Ingest OpenAlex abstracts (explicit abstract_only) -------------
    for rec in out.openalex_works:
        body = rec.abstract or rec.title
        meta = to_knowledge_metadata(rec)
        try:
            res = store.ingest_bytes(
                (body or "").encode("utf-8") or rec.title.encode("utf-8"),
                source_type="web",
                url=rec.landing_url or rec.full_text_url,
                title=rec.title or "openalex work",
                origin_id=f"doi:{rec.doi}" if rec.doi else rec.openalex_id,
                mime_type="text/plain",
                workspace_id=workspace_id,
                published_at=rec.publication_date,
                metadata=meta,
            )
            if res.chunk_ids:
                out.ingested += 1
                out.by_source["openalex"] = out.by_source.get("openalex", 0) + 1
                out.details.append({
                    "source": "openalex", "doi": rec.doi, "read_level": "abstract_only",
                    "document_id": res.document_id, "title": rec.title[:80],
                })
            else:
                out.failed += 1
        except Exception as exc:  # noqa: BLE001
            out.failed += 1
            out.details.append({"source": "openalex", "error": type(exc).__name__})

    # --- Fetch search originals (publisher pages / PDFs) ----------------
    budget = max_yandex_docs
    for hit in yandex_hits:
        if budget <= 0:
            break
        origin_prefix = _hit_prefix(hit)
        meta = {
            "source": hit.source or "web_search",
            "query": hit.query,
            "publisher": hit.publisher,
            "claim_type": "lead",
            "research_lead": True,
            "primary_url_candidate": True,
            "read_level": "unknown_until_parse",
            "limitation": "found_via_search_not_verified",
        }
        if not fetch_externals:
            # store the hit as a lead without fetching
            try:
                res = store.ingest_bytes(
                    (hit.snippet or hit.title).encode("utf-8"),
                    source_type="web",
                    url=hit.url,
                    title=hit.title,
                    origin_id=f"{origin_prefix}:{hit.url}",
                    mime_type="text/plain",
                    workspace_id=workspace_id,
                    metadata=meta,
                )
                if res.chunk_ids:
                    out.ingested += 1
                    out.by_source[origin_prefix] = out.by_source.get(origin_prefix, 0) + 1
            except Exception:
                out.failed += 1
            budget -= 1
            continue

        fr = await fetch_document(hit.url)
        out.fetched += 1
        if not fr.ok:
            out.failed += 1
            out.details.append({"url": hit.url, "error": fr.error_code})
            continue
        if not fr.data:
            out.failed += 1
            continue

        is_pdf = _looks_like_pdf(fr)
        # Decode a text slice for provenance (PDF body may be binary)
        sample = b""
        if not is_pdf and fr.data:
            sample = fr.data[:20000]
        body_txt = sample.decode("utf-8", errors="replace") if sample else ""
        if is_pdf and fr.data:
            # cheap PDF text sniff for provenance
            body_txt = re.findall(rb"\(([^)]{4,80})\)", fr.data[:100000])
            body_txt = " ".join(x.decode("latin-1", "replace") if isinstance(x, bytes) else str(x)
                                for x in body_txt)[:4000]
        prov = classify_url(
            fr.final_url or hit.url,
            title=hit.title,
            snippet=hit.snippet,
            body=body_txt,
        )
        meta.update({
            "primary_fetched": True,
            "content_sha256": fr.sha256,
            "final_url": fr.final_url,
            "read_level": "full_text" if is_pdf else "html_or_text",
            **provenance_meta(prov),
        })
        try:
            res = store.ingest_bytes(
                fr.data,
                source_type="web",
                url=hit.url,
                title=hit.title,
                origin_id=f"sha256:{fr.sha256}" if fr.sha256 else f"{origin_prefix}:{hit.url}",
                mime_type=fr.content_type or ("application/pdf" if is_pdf else "text/html"),
                filename=hit.title[:40] + (".pdf" if is_pdf else ".html"),
                workspace_id=workspace_id,
                metadata=meta,
            )
            if res.chunk_ids:
                out.ingested += 1
                out.by_source[origin_prefix] = out.by_source.get(origin_prefix, 0) + 1
                out.by_source[f"kind:{prov.kind}"] = out.by_source.get(f"kind:{prov.kind}", 0) + 1
                out.details.append({
                    "source": hit.source or "web_search", "url": hit.url,
                    "read_level": meta["read_level"], "document_id": res.document_id,
                    "source_kind": prov.kind,
                    "primary_parsed": prov.primary_parsed,
                    "supports_claim": prov.supports_claim,
                })
            else:
                out.failed += 1
                out.details.append({"url": hit.url, "errors": res.errors, "parse": res.parse_status})
        except Exception as exc:  # noqa: BLE001
            out.failed += 1
            out.details.append({"url": hit.url, "error": type(exc).__name__})
        budget -= 1

    if not out.yandex_hits and not out.openalex_works:
        out.limitations.append("no_evidence_in_allowed_corpus")
    return out
