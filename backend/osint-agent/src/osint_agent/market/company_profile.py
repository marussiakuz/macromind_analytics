"""Universal company profile extraction (2026-10-22).

No hardcoded company, site, industry, or competitor list.
Inputs come from registry/Checko/site text/OpenAlex — whatever is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass
class ProductDirection:
    name: str
    status: str  # confirmed | needs_clarification
    buyers: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    source: str = "okved"  # site | registry | finance | unknown
    confidence: str = "low"


@dataclass
class CompanyProfile:
    inn: str
    name: str | None = None
    full_name: str | None = None
    okved: str | None = None
    okved_description: str | None = None
    official_site: str | None = None
    site_status: str = "not_searched"  # not_searched | found | verified | not_found | ambiguous
    site_checks: list[str] = field(default_factory=list)
    directions: list[ProductDirection] = field(default_factory=list)
    needs_product_clarification: bool = True
    multi_product: bool = False
    gaps: list[str] = field(default_factory=list)

    def primary_direction(self) -> ProductDirection | None:
        for d in self.directions:
            if d.status == "confirmed":
                return d
        return self.directions[0] if self.directions else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inn": self.inn,
            "name": self.name,
            "full_name": self.full_name,
            "okved": self.okved,
            "okved_description": self.okved_description,
            "official_site": self.official_site,
            "site_status": self.site_status,
            "site_checks": self.site_checks,
            "directions": [
                {
                    "name": d.name,
                    "status": d.status,
                    "buyers": d.buyers,
                    "applications": d.applications,
                    "evidence_ids": d.evidence_ids,
                    "source": d.source,
                    "confidence": d.confidence,
                }
                for d in self.directions
            ],
            "needs_product_clarification": self.needs_product_clarification,
            "multi_product": self.multi_product,
            "gaps": self.gaps,
        }


_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
_PRODUCT_HINTS = (
    "продукция", "услуги", "производит", "изготавливает", "поставляет", "внедряет",
    "разрабатывает", "product", "services", "manufactures", "supplies", "software",
    "решение", "платформа", "сервис",
)
_BUYER_HINTS = (
    "клиент", "заказчик", "покупатель", "для банков", "для ритейла", "b2b", "b2g",
    "customer", "clients", "for enterprises", "для предприятий",
)


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = (x or "").strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def extract_urls(*texts: str | None) -> list[str]:
    urls: list[str] = []
    for t in texts:
        if not t:
            continue
        urls.extend(_URL_RE.findall(str(t)))
    cleaned = []
    for u in urls:
        u = u.rstrip(".,;)")
        host = (urlparse(u).hostname or "").lower()
        if any(bad in host for bad in ("t.me", "telegram", "vk.com", "facebook", "youtube")):
            continue
        cleaned.append(u)
    return _unique_keep_order(cleaned)


def score_official_site(company_name: str | None, urls: list[str]) -> tuple[str | None, str, list[str]]:
    """Pick official site from candidate URLs. Never hardcode domains."""
    checks: list[str] = []
    if not urls:
        return None, "not_found", ["no_urls_in_sources"]
    name_tokens = [
        t.lower() for t in re.findall(r"[a-zа-яё]{3,}", (company_name or ""), flags=re.I | re.U)
        if t.lower() not in {"ооо", "зао", "пао", "ао", "ип", "the", "llc"}
    ]
    best: tuple[int, str] | None = None
    for u in urls:
        host = (urlparse(u).hostname or "").removeprefix("www.").lower()
        score = 0
        for tok in name_tokens:
            if tok in host or tok in u.lower():
                score += 2
        if host.endswith(".ru") or host.endswith(".рф"):
            score += 1
        if any(x in host for x in ("about", "press", "ir.", "investor")):
            score += 1
        # prefer bare corporate domain over deep path
        path = urlparse(u).path or ""
        if path in ("", "/"):
            score += 1
        checks.append(f"{u} score={score}")
        if best is None or score > best[0]:
            best = (score, u)
    if best is None or best[0] <= 0:
        return urls[0] if urls else None, "ambiguous", checks
    if best[0] >= 3:
        return best[1], "verified", checks
    return best[1], "found", checks


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 8]


def extract_directions_from_text(
    text: str,
    *,
    okved_description: str | None = None,
    max_directions: int = 5,
) -> list[ProductDirection]:
    """Heuristic product/buyer extraction. No industry dictionary in code."""
    dirs: list[ProductDirection] = []
    seen: set[str] = set()
    sentences = split_sentences(text or "")

    for sent in sentences:
        low = sent.lower()
        if not any(h in low for h in _PRODUCT_HINTS):
            continue
        # take noun-ish phrase after hint
        for hint in _PRODUCT_HINTS:
            idx = low.find(hint)
            if idx < 0:
                continue
            tail = sent[idx + len(hint):].strip(" :,-–—")
            phrase = tail.split(".")[0].split(";")[0][:80].strip()
            if len(phrase) < 4:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            buyers = [
                s.strip()[:60]
                for s in sent.split(",")
                if any(b in s.lower() for b in _BUYER_HINTS)
            ][:3]
            dirs.append(ProductDirection(
                name=phrase,
                status="needs_clarification",
                buyers=buyers,
                applications=[],
                source="site",
                confidence="medium",
            ))
            if len(dirs) >= max_directions:
                return dirs

    if not dirs and okved_description:
        dirs.append(ProductDirection(
            name=okved_description[:100],
            status="needs_clarification",
            source="okved",
            confidence="low",
        ))
    return dirs


def build_company_profile(
    company: dict[str, Any],
    *,
    site_text: str | None = None,
    extra_sources: list[str] | None = None,
    known_urls: list[str] | None = None,
) -> CompanyProfile:
    inn = str(company.get("inn") or company.get("ИНН") or "")
    name = company.get("name") or company.get("short_name") or company.get("полное_наименование")
    full_name = company.get("full_name") or company.get("name_full")
    okved = company.get("okved_main") or company.get("ОКВЭД") or company.get("okved")
    okved_desc = company.get("okved_description") or company.get("ОКВЭД_текст")

    urls = extract_urls(
        site_text,
        *(extra_sources or []),
        company.get("site"),
        company.get("website"),
        company.get("url"),
        # Checko contacts (company.md / UI checkResult.js)
        (company.get("contacts") or {}).get("ВебСайт"),
        (company.get("contacts") or {}).get("Сайт"),
        (company.get("contacts") or {}).get("website"),
        *(known_urls or []),
    )
    site, site_status, checks = score_official_site(
        name or full_name or "",
        urls,
    )

    profile = CompanyProfile(
        inn=inn,
        name=name,
        full_name=full_name,
        okved=str(okved) if okved else None,
        okved_description=okved_desc,
        official_site=site,
        site_status=site_status,
        site_checks=checks,
    )

    dirs = extract_directions_from_text(
        site_text or "",
        okved_description=okved_desc,
    )
    # also allow explicitly provided product fields from registry
    for key in ("products", "product_names", "product_lines"):
        for p in (company.get(key) or [])[:5]:
            if isinstance(p, dict):
                pname = p.get("name") or p.get("product")
            else:
                pname = str(p)
            if pname:
                dirs.append(ProductDirection(
                    name=str(pname)[:100],
                    status="needs_clarification",
                    source="registry",
                    confidence="medium",
                ))

    # dedupe by name
    uniq: list[ProductDirection] = []
    seen: set[str] = set()
    for d in dirs:
        k = d.name.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(d)
    profile.directions = uniq[:5]
    profile.multi_product = len(profile.directions) > 1
    profile.needs_product_clarification = not any(
        d.status == "confirmed" for d in profile.directions
    ) or profile.multi_product

    if site_status in ("not_found", "ambiguous"):
        profile.gaps.append("official_site")
    if not profile.directions:
        profile.gaps.append("product_definition")
    if profile.multi_product:
        profile.gaps.append("multiple_products_choose_direction")
    return profile
