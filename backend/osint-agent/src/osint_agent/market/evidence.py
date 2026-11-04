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
from osint_agent.market.providers.search_factory import get_search_provider

# бюджет исследования (spec §5.3)
MAX_YANDEX_QUERIES = 3
MAX_OPENALEX_QUERIES = 2
MAX_ITEMS_PER_SOURCE = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_of(page: Any, provider: Any = None) -> str:
    """Фактический источник страницы поиска (происхождение записей)."""
    return (getattr(page, "source", "") or getattr(provider, "name", "") or "web_search")


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


def build_search_queries(company: dict[str, Any]) -> list[dict[str, Any]]:
    """Ограниченный набор запросов (spec §5.1 п.3).

    Обязательная проверка двух языков: русские запросы — для российских источников,
    английские (с переводом продукта и применения) — для мировых. Один не заменяет другой.
    """
    name = (company.get("name") or company.get("full_name") or "").strip()
    name_en = (company.get("name_en") or "").strip()
    product_en = (company.get("product_en") or "").strip()
    okved = (company.get("okved_description") or "").strip()
    qs: list[dict[str, Any]] = []
    if name:
        qs.append({"query": f"{name} рынок услуги", "region": "RU", "lang": "ru"})
    if okved:
        qs.append({"query": f"{okved} объем рынка Россия", "region": "RU", "lang": "ru"})
    if not qs:
        qs.append({"query": "рынок услуг России объем", "region": "RU", "lang": "ru"})
    en_subject = product_en or name_en
    if en_subject:
        qs.append({"query": f"{en_subject} market services", "region": "COM", "lang": "en"})
        if okved:
            qs.append({"query": f"{okved} market size", "region": "COM", "lang": "en"})
    return qs[:MAX_YANDEX_QUERIES + 2]


def build_science_queries(company: dict[str, Any]) -> list[str]:
    okved = (company.get("okved_description") or company.get("okved_main") or "financial services").strip()
    return [f"{okved}"][:MAX_OPENALEX_QUERIES]


def normalize_url_key(url: str) -> str:
    """Ключ дедупликации: нормализованный URL без изменения пути и значимых параметров."""
    try:
        p = urlparse((url or "").strip())
    except Exception:
        return (url or "").strip().lower()
    if not p.scheme or not p.netloc:
        return (url or "").strip().lower()
    host = p.netloc.lower()
    if host.endswith(":80") and p.scheme == "http":
        host = host[:-3]
    if host.endswith(":443") and p.scheme == "https":
        host = host[:-4]
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = p.query
    return f"{host}{path}" + (f"?{query}" if query else "")


def _dedupe_by_url(evidence: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Один документ, найденный двумя поисковиками, не даёт двух подтверждений (MIMO_TAVILY_SETUP п.4)."""
    seen: dict[str, str] = {}
    unique: list[dict[str, Any]] = []
    duplicates = 0
    for e in evidence:
        key = normalize_url_key(e.get("url") or "")
        if key and key in seen:
            e["duplicate_of"] = seen[key]
            duplicates += 1
            continue
        if key:
            seen[key] = e["id"]
        unique.append(e)
    return unique, duplicates


def _item_text(it: dict[str, Any]) -> str:
    """Текстовая выдержка результата поиска из любого поставщика."""
    passage = (it.get("passage") or "").strip()
    if passage:
        return passage
    highlights = it.get("highlights")
    if isinstance(highlights, str):
        highlights = [highlights]
    if isinstance(highlights, list):
        joined = "\n".join(str(h).strip() for h in highlights if str(h or "").strip()).strip()
        if joined:
            return joined
    return (it.get("content") or it.get("snippet") or "").strip()


def _evidence_from_search(items: list[dict[str, Any]], query: str, provider: str = "yandex_search") -> list[dict[str, Any]]:
    """Normalize search results to evidence. provider identifies the actual source (§4).

    Backward compat: old IDs used 'yandex:' prefix. New IDs use actual provider name
    (exa:* с source_id=exa_search, tavily:* с source_id=tavily_search).
    """
    prefix = "yandex" if provider == "yandex_search" else provider.replace("_search", "")
    out = []
    for i, it in enumerate(items[:MAX_ITEMS_PER_SOURCE]):
        url = it.get("url") or ""
        passage = _item_text(it)
        title = (it.get("title") or "").strip()
        published = it.get("published_date") or it.get("publication_date") or None
        out.append(
            {
                "id": f"{prefix}:{snippet_fingerprint(url + title)}",
                "type": "web_snippet",
                "source_id": provider,
                "title": title,
                "url": url if is_public_http_url(url) else None,
                "locator": f"search_result[{i}]",
                "quote": passage[:500],
                "full_text_read": False,  # F17
                "fetched_at": _now(),
                "query": query,
                "completeness": "snippet_only" if passage else "no_text",
                "read_level": "snippet_only" if passage else "metadata_only",
                "publication_date": published,
                "limitations": (
                    ["Только выдержка поиска; полный документ не читался"]
                    if passage
                    else ["Метаданные без текста; подтверждение содержания невозможно"]
                ),
            }
        )
    return out


# Backward-compatible alias
_evidence_from_yandex = lambda items, query: _evidence_from_search(items, query, "yandex_search")


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


async def collect_market_evidence(company: dict[str, Any], llm_unused=None, budget=None) -> dict[str, Any]:
    """Сбор фактуры. Ошибки/квоты ≠ пустой успех (F20).

    company.search_queries — явные запросы (похожие компании + рынок);
    иначе build_search_queries(company).
    budget — ResearchBudget: общий учёт квот и расходов исследования.
    """
    states: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    search_queries = company.get("search_queries")
    if search_queries is None:
        search_queries = build_search_queries(company)
    science_queries = company.get("science_queries") or build_science_queries(company)

    search = get_search_provider(budget=budget)
    try:
        planned: list[dict[str, Any]] = []
        for q in search_queries[:8]:
            if isinstance(q, dict):
                region = q.get("region", "RU") or "RU"
                planned.append({
                    "query": q.get("query", ""),
                    "region": region,
                    "lang": q.get("lang") or ("en" if region == "COM" else "ru"),
                })
            else:
                planned.append({"query": q, "region": "RU", "lang": "ru"})

        def _not_executed(rest: list[dict[str, Any]], reason: str) -> None:
            for item in rest:
                states.append({
                    "source": getattr(search, "name", "") or "web_search",
                    "status": "not_executed",
                    "query": item["query"],
                    "lang": item["lang"],
                    "region": item["region"],
                    "message": f"Запрос не выполнен: {reason}",
                })

        for idx, item in enumerate(planned):
            page = await search.search(item["query"], filters={"region": item["region"]}, budget=5)
            states.append(
                {
                    "source": source_of(page, search),
                    "status": page.status.value,
                    "query": item["query"],
                    "lang": item["lang"],
                    "region": item["region"],
                    "count": len(page.items),
                    "message": page.message,
                    "coverage": page.coverage,
                }
            )
            if page.status in (SourceStatus.ok, SourceStatus.partial):
                evidence.extend(_evidence_from_search(page.items, item["query"], source_of(page, search)))
            if page.status in (SourceStatus.not_configured, SourceStatus.rate_limited):
                # Невыполненная часть поиска показывается явно, а не замалчивается.
                _not_executed(planned[idx + 1:], page.status.value)
                break

        # Режим «нехватка доказательств»: конкретные дополнительные запросы
        # в пределах остаточного бюджета запасного поиска (MIMO_TAVILY_SETUP п.3).
        if hasattr(search, "search_backup") and len([e for e in evidence if e.get("quote")]) < 4:
            name = (company.get("name") or company.get("full_name") or "").strip()
            name_en = (company.get("name_en") or "").strip()
            product_en = (company.get("product_en") or "").strip()
            okved = (company.get("okved_description") or "").strip()
            extra: list[dict[str, Any]] = []
            if name:
                extra.append({"query": f'"{name}" продукция применение рынок', "lang": "ru"})
                if okved:
                    extra.append({"query": f'"{name}" {okved} конкуренты рынок', "lang": "ru"})
            en_subject = product_en or name_en
            if en_subject:
                extra.append({"query": f'"{en_subject}" products applications market', "lang": "en"})
            for item in extra[:2]:
                page = await search.search_backup(item["query"], budget=5)
                states.append(
                    {
                        "source": source_of(page, search),
                        "status": page.status.value,
                        "query": item["query"],
                        "lang": item["lang"],
                        "count": len(page.items),
                        "message": page.message,
                        "coverage": page.coverage,
                        "supplementary": True,
                    }
                )
                if page.status in (SourceStatus.ok, SourceStatus.partial):
                    evidence.extend(_evidence_from_search(page.items, item["query"], source_of(page, search)))
    finally:
        await search.aclose()

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
    unique, url_duplicates = _dedupe_by_url(unique)
    duplicates += url_duplicates
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
