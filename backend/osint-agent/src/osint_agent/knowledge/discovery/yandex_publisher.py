"""Yandex Search → publisher pages / original reports (MIMO_DISCOVERY §3.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class DiscoveryHit:
    query: str
    lang: str
    title: str
    url: str
    snippet: str = ""
    source: str = "yandex"
    publisher: str | None = None
    is_pdf: bool = False
    original_url_candidate: str | None = None


PUBLISHER_HINTS = (
    "research", "report", "analytics", "insight", "whitepaper",
    "исследован", "отчет", "аналитик", "обзор",
)
AD_HINTS = ("купить", "заказать", "price", "pricing", "buy now", "download sample", "request sample")


def _publisher_from_url(url: str) -> str | None:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.") or None


def is_likely_paid_landing(url: str, title: str, snippet: str) -> bool:
    blob = f"{url} {title} {snippet}".lower()
    return any(h in blob for h in AD_HINTS) and not any(h in blob for h in PUBLISHER_HINTS)


async def search_yandex(
    queries: list[dict],
    *,
    provider=None,
    budget_per_query: int = 8,
) -> list[DiscoveryHit]:
    """Run product-profile queries through the existing YandexSearchProvider."""
    from osint_agent.market.providers.web_search import YandexSearchProvider

    y = provider or YandexSearchProvider()
    hits: list[DiscoveryHit] = []
    try:
        for qd in queries:
            q = qd.get("query") or ""
            if not q:
                continue
            try:
                page = await y.search(q, budget=budget_per_query)
            except Exception:
                continue
            for it in (getattr(page, "items", None) or []):
                url = it.get("url") or it.get("link") or ""
                title = it.get("title") or ""
                snippet = it.get("snippet") or it.get("description") or ""
                if not url:
                    continue
                # prefer publisher page over aggregator ad
                if is_likely_paid_landing(url, title, snippet):
                    continue
                hits.append(DiscoveryHit(
                    query=q,
                    lang=qd.get("lang") or "ru",
                    title=title[:300],
                    url=url,
                    snippet=snippet[:1000],
                    publisher=_publisher_from_url(url),
                    is_pdf=bool(re.search(r"\.pdf($|\?)", url.lower())) or "pdf" in title.lower(),
                    original_url_candidate=url,
                ))
    finally:
        close = getattr(y, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass
    # dedupe by URL
    seen: set[str] = set()
    out: list[DiscoveryHit] = []
    for h in hits:
        if h.url in seen:
            continue
        seen.add(h.url)
        out.append(h)
    return out
