"""OpenAlex works collector with DOI dedup (MIMO_DISCOVERY / user 2026-10-22).

Saves DOI, authors, date, abstract, full-text link.
Marks read_level: abstract_only | full_text.
Never treats citation/publish counts as market-growth proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from osint_agent.market.providers.openalex import OpenAlexProvider, rebuild_abstract


@dataclass
class WorkRecord:
    doi: str | None
    openalex_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    publication_date: str | None = None
    abstract: str | None = None
    full_text_url: str | None = None
    landing_url: str | None = None
    primary_topic: str | None = None
    cited_by_count: int = 0
    read_level: str = "abstract_only"  # abstract_only | full_text
    source: str = "openalex"


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = str(doi).strip().lower()
    if d.startswith("https://doi.org/"):
        d = d[len("https://doi.org/"):]
    if d.startswith("http://doi.org/"):
        d = d[len("http://doi.org/"):]
    if d.startswith("doi:"):
        d = d[4:]
    return d or None


def _authors_of(work: dict[str, Any]) -> list[str]:
    out = []
    for a in (work.get("authorships") or [])[:20]:
        name = (a.get("author") or {}).get("display_name")
        if name:
            out.append(name)
    return out


def _fulltext_url(work: dict[str, Any]) -> str | None:
    primary = work.get("primary_location") or {}
    if primary.get("pdf_url"):
        return primary["pdf_url"]
    oa = work.get("open_access") or {}
    url = oa.get("oa_url")
    if url:
        return url
    for loc in (work.get("locations") or [])[:10]:
        pdf = loc.get("pdf_url") or (loc.get("source") or {}).get("url")
        if loc.get("is_oa") and pdf:
            return pdf
        if loc.get("pdf_url"):
            return loc["pdf_url"]
    best = work.get("best_oa_location") or {}
    return best.get("pdf_url") or best.get("landing_page_url")


def parse_work(work: dict[str, Any]) -> WorkRecord:
    abstract = work.get("abstract")
    try:
        abstract = abstract or rebuild_abstract(work.get("abstract_inverted_index"))
    except Exception:
        abstract = None
    doi = _norm_doi(work.get("doi"))
    title = (work.get("title") or work.get("display_name") or "")[:300]
    return WorkRecord(
        doi=doi,
        openalex_id=str(work.get("id") or ""),
        title=title,
        authors=_authors_of(work),
        publication_date=work.get("publication_date") or str(work.get("publication_year") or ""),
        abstract=(abstract or "")[:20000] or None,
        full_text_url=_fulltext_url(work),
        landing_url=(work.get("primary_location") or {}).get("landing_page_url"),
        primary_topic=((work.get("primary_topic") or {}).get("display_name")),
        cited_by_count=int(work.get("cited_by_count") or 0),
        read_level="abstract_only" if abstract else "metadata_only",
    )


async def collect_openalex(
    terms: list[str],
    *,
    provider: OpenAlexProvider | None = None,
    budget_per_query: int = 10,
) -> list[WorkRecord]:
    """Search works; dedupe strictly by DOI (fallback openalex_id)."""
    p = provider or OpenAlexProvider()
    by_key: dict[str, WorkRecord] = {}
    try:
        for term in terms:
            if not term:
                continue
            try:
                page = await p.search(term, budget=budget_per_query)
            except Exception:
                continue
            for it in (getattr(page, "items", None) or []):
                rec = parse_work(it if isinstance(it, dict) else {})
                key = rec.doi or rec.openalex_id
                if not key or key in by_key:
                    continue
                by_key[key] = rec
    finally:
        close = getattr(p, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass
    return list(by_key.values())


def to_knowledge_metadata(rec: WorkRecord) -> dict[str, Any]:
    """Metadata for document store. Citation count is NOT market evidence."""
    return {
        "doi": rec.doi,
        "openalex_id": rec.openalex_id,
        "authors": rec.authors,
        "publication_date": rec.publication_date,
        "abstract": (rec.abstract or "")[:4000],
        "full_text_url": rec.full_text_url,
        "landing_url": rec.landing_url,
        "primary_topic": rec.primary_topic,
        "cited_by_count": rec.cited_by_count,
        "read_level": rec.read_level,
        "source": rec.source,
        "limitation": "citations_are_not_market_growth",
        "research_lead": True,
        "claim_type": "lead",
    }
