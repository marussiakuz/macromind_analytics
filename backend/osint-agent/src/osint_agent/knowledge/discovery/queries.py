"""Build RU/EN search queries from a product profile (MIMO_DISCOVERY §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductProfile:
    product: str
    category: str | None = None
    buyers: str | None = None
    geography: str = "Россия"
    year_from: int | None = None
    year_to: int | None = None
    extra_terms: list[str] = field(default_factory=list)

    @classmethod
    def from_analysis(cls, summary: dict[str, Any] | None) -> "ProductProfile":
        summary = summary or {}
        scope = summary.get("product_scope") or summary.get("market_scope") or {}
        product = (
            scope.get("product")
            or scope.get("okved_description")
            or summary.get("product")
            or "software market"
        )
        geo = scope.get("geography") or summary.get("geography") or "Россия"
        years = summary.get("reference_period") or {}
        y_from = years.get("from") if isinstance(years, dict) else None
        y_to = years.get("to") if isinstance(years, dict) else None
        return cls(
            product=str(product),
            category=scope.get("category"),
            buyers=scope.get("buyers") or scope.get("customer"),
            geography=str(geo),
            year_from=y_from,
            year_to=y_to,
        )


def _years(p: ProductProfile) -> str:
    y_from = p.year_from or 2024
    y_to = p.year_to or 2026
    return f"{y_from} {y_to}"


def build_queries(profile: ProductProfile) -> list[dict]:
    """Return [{lang, kind, query}] — RU + EN, filetype:pdf as extra not hard filter."""
    prod = profile.product.strip()
    geo = profile.geography.strip() or "Россия"
    years = _years(profile)
    buyers = (profile.buyers or "").strip()
    extra = " ".join(profile.extra_terms)

    ru = [
        {"lang": "ru", "kind": "market_report", "query": f"рынок {prod} {geo} исследование отчет {years}"},
        {"lang": "ru", "kind": "market_report_pdf", "query": f"{prod} {geo} исследование filetype:pdf"},
        {"lang": "ru", "kind": "vendors", "query": f"{prod} поставщики обзор рынка {geo}"},
        {"lang": "ru", "kind": "adoption", "query": f"внедрение {prod} опрос отчет {years}"},
    ]
    if buyers:
        ru.append({"lang": "ru", "kind": "buyers", "query": f"{prod} {buyers} исследование спроса"})

    en = [
        {"lang": "en", "kind": "market_report", "query": f"{prod} market research report {years} {geo}"},
        {"lang": "en", "kind": "market_report_pdf", "query": f"{prod} market report filetype:pdf"},
        {"lang": "en", "kind": "adoption", "query": f"enterprise {prod} adoption survey report"},
        {"lang": "en", "kind": "vendors", "query": f"{prod} vendors comparison analyst report"},
    ]
    if extra:
        ru.append({"lang": "ru", "kind": "extra", "query": f"{prod} {extra} отчет"})
        en.append({"lang": "en", "kind": "extra", "query": f"{prod} {extra} report"})
    return ru + en


def openalex_search_terms(profile: ProductProfile) -> list[str]:
    """Short terms for OpenAlex works.search (abstract/title)."""
    prod = profile.product.strip()
    return [
        prod,
        f"{prod} market",
        f"{prod} adoption",
        f"{profile.geography} {prod}",
    ]
