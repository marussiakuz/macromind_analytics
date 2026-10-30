"""Collect market evidence from Yandex Search + OpenAlex (spec Task1 §5).

Snippets are not full documents (F17). No abstract ≠ missing work (F18).
Source states: ok | empty | partial | error | not_configured | rate_limited.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from osint_agent.market.providers.base import SourceStatus
from osint_agent.market.providers.openalex import OpenAlexProvider
from osint_agent.market.providers.web_search import YandexSearchProvider

# бюджет исследования (spec §5.3)
MAX_YANDEX_QUERIES = 3
MAX_OPENALEX_QUERIES = 2
MAX_ITEMS_PER_SOURCE = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_public_http_url(url: str) -> bool:
    """F22: блокируем localhost/частные сети и не-http схемы."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = p.hostname or ""
    if not host or host.lower() in ("localhost", "127.0.0.1", "::1"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        # имя хоста — не IP; доп. DNS-резолв не выполняем здесь
        if host.endswith(".local") or host.endswith(".internal"):
            return False
    return True


def snippet_fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip()[:400]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def build_search_queries(company: dict[str, Any]) -> list[str]:
    """Ограниченный набор запросов (spec §5.1 п.3)."""
    name = (company.get("name") or company.get("full_name") or "").strip()
    okved = (company.get("okved_description") or "").strip()
    qs = []
    if name:
        qs.append(f"{name} рынок услуги")
    if okved:
        qs.append(f"{okved} объем рынка Россия")
    if not qs:
        qs.append("рынок услуг России объем")
    return qs[:MAX_YANDEX_QUERIES]


def build_science_queries(company: dict[str, Any]) -> list[str]:
    okved = (company.get("okved_description") or company.get("okved_main") or "financial services").strip()
    return [f"{okved}"][:MAX_OPENALEX_QUERIES]


def _evidence_from_yandex(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    out = []
    for i, it in enumerate(items[:MAX_ITEMS_PER_SOURCE]):
        url = it.get("url") or ""
        passage = (it.get("passage") or "").strip()
        title = (it.get("title") or "").strip()
        out.append(
            {
                "id": f"yandex:{snippet_fingerprint(url + title)}",
                "type": "web_snippet",
                "source_id": "yandex_search",
                "title": title,
                "url": url if is_public_http_url(url) else None,
                "locator": f"search_result[{i}]",
                "quote": passage[:500],
                "full_text_read": False,  # F17
                "fetched_at": _now(),
                "query": query,
                "completeness": "snippet_only",
                "read_level": "snippet_only",
                "limitations": ["Только выдержка поиска; полный документ не читался"],
            }
        )
    return out


def _evidence_from_openalex(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    out = []
    for it in items[:MAX_ITEMS_PER_SOURCE]:
        abstract = it.get("abstract")
        authorships = it.get("authorships") or []
        authors = []
        for a in authorships[:10] if isinstance(authorships, list) else []:
            name = ((a or {}).get("author") or {}).get("display_name")
            if name:
                authors.append(name)
        out.append(
            {
                "id": f"openalex:{snippet_fingerprint(str(it.get('id') or it.get('doi') or it.get('title')))}",
                "type": "scientific_work",
                "source_id": "openalex",
                "title": it.get("title"),
                "url": it.get("doi") or it.get("id"),
                "doi": it.get("doi"),
                "authors": authors,
                "locator": "works.results",
                "quote": (abstract or "")[:5000] or None,
                "abstract": (abstract or "")[:20000] or None,
                "full_text_read": False,
                "read_level": "abstract_only" if abstract else "metadata_only",
                "fetched_at": _now(),
                "query": query,
                "publication_date": it.get("publication_date"),
                "completeness": "full" if abstract else "no_abstract",  # F18
                "limitations": (
                    ["Аннотация, не полная статья", "Цитирования ≠ рост рынка"]
                    if abstract
                    else ["Аннотация отсутствует; работа сохранена как неполная",
                          "Цитирования ≠ рост рынка"]
                ),
            }
        )
    return out


def _dedupe_reprints(evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """F19: перепечатки одного фрагмента не считаются независимыми."""
    seen: dict[str, str] = {}
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for e in evidence:
        key = snippet_fingerprint(e.get("quote") or e.get("title") or e.get("url") or e["id"])
        if key in seen:
            e["duplicate_of"] = seen[key]
            duplicates += 1
            continue
        seen[key] = e["id"]
        unique.append(e)
    return unique, duplicates


async def collect_market_evidence(company: dict[str, Any], llm_unused=None) -> dict[str, Any]:
    """Сбор фактуры. Ошибки/квоты ≠ пустой успех (F20).

    company.search_queries — явные запросы (похожие компании + рынок);
    иначе build_search_queries(company).
    """
    states: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    yandex_queries = company.get("search_queries") or build_search_queries(company)
    science_queries = company.get("science_queries") or build_science_queries(company)

    yandex = YandexSearchProvider()
    try:
        for q in yandex_queries[:8]:
            region = q.get("region", "RU") if isinstance(q, dict) else "RU"
            q = q.get("query", "") if isinstance(q, dict) else q
            page = await yandex.search(q, filters={"region": region}, budget=5)
            states.append(
                {
                    "source": "yandex_search",
                    "status": page.status.value,
                    "query": q,
                    "count": len(page.items),
                    "message": page.message,
                    "coverage": page.coverage,
                }
            )
            if page.status in (SourceStatus.ok, SourceStatus.partial):
                evidence.extend(_evidence_from_yandex(page.items, q))
            if page.status in (SourceStatus.not_configured, SourceStatus.rate_limited):
                break
    finally:
        await yandex.aclose()

    openalex = OpenAlexProvider()
    try:
        for q in science_queries[:4]:
            page = await openalex.search(q, budget=5)
            states.append(
                {
                    "source": "openalex",
                    "status": page.status.value,
                    "query": q,
                    "count": len(page.items),
                    "message": page.message,
                    "coverage": page.coverage,
                }
            )
            if page.status in (SourceStatus.ok, SourceStatus.partial):
                evidence.extend(_evidence_from_openalex(page.items, q))
            if page.status in (SourceStatus.not_configured, SourceStatus.rate_limited):
                break
    finally:
        await openalex.aclose()

    unique, duplicates = _dedupe_reprints(evidence)
    limitations = []
    if duplicates:
        limitations.append(f"Удалено дублей/перепечаток: {duplicates} (не независимые подтверждения)")
    if any(s["status"] in ("error", "rate_limited", "unavailable") for s in states):
        limitations.append("Часть источников недоступна — полнота фактуры ограничена")
    if any(s["status"] == "not_configured" for s in states):
        limitations.append("Источник не настроен — факты из него отсутствуют")

    return {
        "source_states": states,
        "evidence": unique,
        "duplicates_removed": duplicates,
        "limitations": limitations,
    }


def market_estimates_from_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """F16: если в выдержке есть числовая оценка рынка — сохраняем с ограничениями."""
    found = []
    for e in evidence:
        text = e.get("quote") or ""
        m = re.search(r"(\d+[.,]?\d*)\s*(млрд|млн|миллиард|миллион)", text, re.I)
        if not m:
            continue
        found.append(
            {
                "evidence_id": e["id"],
                "raw_value": m.group(0),
                "period": e.get("publication_date"),
                "geography": "RU",
                "unit": "RUB",
                "status": "unverified_snippet",
                "limitations": [
                    "Значение из поисковой выдержки; полный документ не проверялся",
                ],
            }
        )
    return found
