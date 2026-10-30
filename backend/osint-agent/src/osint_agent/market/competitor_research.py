"""Stage B competitor research (2026-10-23).

Per-direction queries, candidate verification, relation classes.
Expands _collect_competitor_product_pages conceptually; does not invent parallel
competing collectors for the same job.

Relation classes (plan §3 step 5):
  1. direct_competitor  — product AND buyers/territory intersection confirmed
  2. product_analog     — similar product, sales intersection not proven
  3. supplier_partner   — supplier/partner/distributor relation found
  4. candidate_for_check — not enough evidence yet
  5. rejected           — explicit reason
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

RELATION_CLASSES = (
    "direct_competitor",
    "product_analog",
    "supplier_partner",
    "candidate_for_check",
    "rejected",
)

# Hard reasons for rejection (plan §3 step 5).
_REJECT_SELF = "self_company"
_REJECT_NO_EVIDENCE = "insufficient_evidence"
_REJECT_WRONG_RELATION = "supplier_or_partner_not_competitor"
_REJECT_NO_PRODUCT_OVERLAP = "product_overlap_not_shown"
_REJECT_DUPLICATE = "duplicate_company"
_REJECT_DIRECTION_MISMATCH = "different_direction"

_MAX_RU = 10
_MAX_WORLD = 10
_MAX_QUERIES_TOTAL = 24  # plan §6 including existing searches
_SEARCH_BUDGET = 3


def normalize_company_key(name: str) -> str:
    """Identity for dedupe. Legal suffixes are not brand names (plan §3 step 5)."""
    cleaned = re.sub(
        r"\b(?:ооо|оао|зао|пао|ао|ип|нко|ано|гуп|муп|фгуп|"
        r"llc|ltd|inc|corp|corporation|gmbh|ag|sarl|plc|jse|"
        r"компания|группа|холдинг)\b",
        " ",
        str(name or "").lower(),
        flags=re.I | re.U,
    )
    return re.sub(r"[^a-zа-яё0-9]", "", cleaned)


def stop_tokens() -> set[str]:
    return {
        "the", "and", "for", "with", "from", "that", "this", "website", "profile",
        "overview", "leading", "manufacturer", "manufacturers", "supplier", "suppliers",
        "company", "companies", "products", "catalog", "catalogue", "comparison",
        "target", "china", "systems", "hose", "hoses", "parts", "block", "blocks",
        "manifold", "hydraulic", "hydraulics", "innovations", "metoree", "saroit",
    }


def direction_search_queries(direction: dict[str, Any], *, lang: str = "ru") -> list[str]:
    """Query = category + application + role + territory (plan §3 step 4).

    Not OKVED-only. Generic industry lists are discovery only, not proof.
    """
    cat_ru = (direction.get("product_category_ru") or "").strip()
    cat_en = (direction.get("product_category_en") or "").strip()
    apps = [a for a in (direction.get("applications") or []) if a]
    role = (direction.get("role") or "").strip()
    geo = (direction.get("geography") or "").strip() or "Россия"
    if geo.lower() in {"unknown", "неизвестно", ""}:
        geo_ru = "Россия"
    else:
        geo_ru = geo

    # Shorten overlong categories so the query stays a real search phrase.
    cat_short_ru = cat_ru.split("(")[0].strip() or cat_ru
    if len(cat_short_ru) > 48:
        cat_short_ru = " ".join(cat_short_ru.split()[:5])
    cat_short_en = (cat_en or cat_short_ru).split("(")[0].strip()
    if len(cat_short_en) > 48:
        cat_short_en = " ".join(cat_short_en.split()[:5])

    app = apps[0] if apps else ""
    if app and len(app) > 36:
        app = " ".join(app.split()[:3])
    queries: list[str] = []

    if lang == "en" or not cat_ru:
        base = cat_short_en or cat_short_ru or ""
        # Company-like phrases, not directory dumps.
        queries.extend([
            f"{base} manufacturer company official".strip(),
            f"{base} producers suppliers comparison".strip(),
        ])
    else:
        queries.extend([
            f"{cat_short_ru} производители {geo_ru}".strip(),
            f"{cat_short_ru} {app} {geo_ru}".strip() if app else f"{cat_short_ru} аналоги {geo_ru}",
            f"{cat_short_ru} поставщики {geo_ru} аналоги".strip(),
        ])
        if role == "distributor":
            queries.append(f"{cat_short_ru} дистрибьюторы {geo_ru}".strip())
        elif role == "service_provider":
            queries.append(f"{cat_short_ru} услуги компании {geo_ru}".strip())
        else:
            queries.append(f"{cat_short_ru} изготовление на заказ".strip())
        if cat_short_en:
            queries.append(f"{cat_short_en} manufacturers".strip())

    # de-dup, keep order
    out, seen = [], set()
    for q in queries:
        q = re.sub(r"\s+", " ", q).strip()[:120]
        if q and q.casefold() not in seen:
            seen.add(q.casefold())
            out.append(q)
    return out[:4]


def build_relation_candidate(
    *,
    name: str,
    direction_id: str,
    territory: str = "unknown",  # russia | world | unknown
    product: str = "",
    relation_class: str = "candidate_for_check",
    reason: str = "",
    evidence: list[dict[str, Any]] | None = None,
    quotes: list[str] | None = None,
    links: list[str] | None = None,
    applications_match: bool | None = None,
    buyers_match: bool | None = None,
    role_match: bool | None = None,
    territory_status: str = "unknown",  # confirmed | unknown | absent_in_russia
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    rc = relation_class if relation_class in RELATION_CLASSES else "candidate_for_check"
    ev = list(evidence or [])
    if not ev and quotes:
        ev = [{"quote": q[:400]} for q in quotes[:4] if q]
    return {
        "name": str(name or "").strip()[:160],
        "direction_id": direction_id,
        "territory": territory if territory in {"russia", "world", "unknown"} else "unknown",
        "product": (product or "")[:180],
        "relation_class": rc,
        "reason": reason[:500],
        "evidence": ev[:4],
        "links": list(links or [])[:6],
        "match": {
            "product_or_service": True if rc != "rejected" else False,
            "applications": applications_match,
            "buyers": buyers_match,
            "role": role_match,
        },
        "territory_status": territory_status,
        "limitations": list(limitations or []),
    }


def classify_candidate(
    *,
    name: str,
    direction: dict[str, Any],
    own_company_names: list[str],
    supplier_or_partner_names: list[str],
    quotes: list[str],
    territory: str,
    territory_confirmed: bool | None,
    buyers_overlap: bool | None,
    role_compatible: bool | None,
    product_overlap: bool,
) -> dict[str, Any]:
    """Apply plan §3 step 5 relation classes with explicit reasons."""
    did = str(direction.get("direction_id") or "d1")
    product = direction.get("product_category_ru") or direction.get("product_category_en") or ""
    key = normalize_company_key(name)
    own_keys = {normalize_company_key(x) for x in own_company_names if x}
    supplier_keys = {normalize_company_key(x) for x in supplier_or_partner_names if x}
    quote_blob = " ".join(quotes).lower()
    limitations: list[str] = []

    if not name or not key:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="rejected", reason=_REJECT_NO_EVIDENCE,
            limitations=["Пустое или некорректное наименование"],
        )
    if key in own_keys or any(key and (key in ok or ok in key) and len(key) > 4 for ok in own_keys):
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="rejected", reason=_REJECT_SELF,
            limitations=["Исключён: сама изучаемая компания"],
        )

    # Supplier/partner relation requires a link to THIS company (plan §3 step 5 / Astra P1).
    # Self-description "we are a supplier of X" is a role, not a relation to the studied firm.
    is_supplier = key in supplier_keys or any(
        key and (key in sk or sk in key) and len(key) > 4 for sk in supplier_keys
    )
    # Explicit two-party link: candidate + studied company named in the same quote.
    own_display = " ".join(own_company_names)
    relation_to_studied = is_supplier or bool(re.search(
        r"(поставщик|дистрибьютор|дилер|partner|supplier|distributor|dealer|уполномочен)"
        r".{0,80}" + re.escape((own_company_names[0] if own_company_names else "")[:20]),
        quote_blob, re.I,
    )) or bool(
        own_company_names and any(
            normalize_company_key(o) and normalize_company_key(o) in quote_blob
            and re.search(r"поставщик|дистрибьютор|дилер|partner of|supplier of|authorized", quote_blob, re.I)
            for o in own_company_names[:3]
        )
    )
    # Role words only (independent firm's self-description).
    supplier_role_text = bool(re.search(
        r"поставщик|дистрибьютор|дилер|partner|supplier|distributor|dealer",
        quote_blob, re.I,
    ))

    if not product_overlap:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="rejected", reason=_REJECT_NO_PRODUCT_OVERLAP,
            territory_status="confirmed" if territory_confirmed else "unknown",
            limitations=["Не показано совпадение конкретного изделия/услуги"],
        )

    # Foreign product analog is NOT a direct RF competitor (plan §3 step 5 / §3 step 6).
    if territory == "world" and not territory_confirmed:
        if relation_to_studied:
            return build_relation_candidate(
                name=name, direction_id=did, territory=territory, product=product,
                relation_class="supplier_partner",
                reason="Найдено отношение поставщика/партнёра к изучаемой компании",
                quotes=quotes, applications_match=role_compatible,
                role_match=True, territory_status="unknown",
                limitations=["Поставщик/партнёр по направлению, не конкурент"],
            )
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="product_analog",
            reason="Зарубежный продуктовый аналог; продажи в РФ не доказаны",
            quotes=quotes,
            applications_match=buyers_overlap, buyers_match=buyers_overlap,
            role_match=role_compatible, territory_status="unknown",
            limitations=["Не называть прямым конкурентом на российском рынке без доказательств"],
        )

    if relation_to_studied:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="supplier_partner",
            reason="Поставщик/партнёр изучаемой компании, не прямой конкурент",
            quotes=quotes, applications_match=buyers_overlap,
            role_match=True,
            territory_status="confirmed" if territory_confirmed else "unknown",
            limitations=["Отношение оценено в рамках направления " + did],
        )

    # Direct competitor: product + (buyers or territory) intersection confirmed.
    if territory == "russia" and territory_confirmed and buyers_overlap and role_compatible:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="direct_competitor",
            reason="Подтверждено пересечение предложения и покупателей/территории",
            quotes=quotes, applications_match=True, buyers_match=True, role_match=True,
            territory_status="confirmed",
        )
    if territory == "russia" and territory_confirmed and role_compatible and buyers_overlap is None:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="product_analog",
            reason="Сопоставимая продукция в РФ; пересечение покупателей не доказано",
            quotes=quotes, applications_match=None, buyers_match=None, role_match=True,
            territory_status="confirmed",
            limitations=["Покупатели/применение не подтверждены"],
        )
    if product_overlap and (buyers_overlap or role_compatible):
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="product_analog",
            reason="Сопоставимая продукция; пересечение продаж не доказано",
            quotes=quotes, applications_match=buyers_overlap,
            buyers_match=buyers_overlap, role_match=role_compatible,
            territory_status="confirmed" if territory_confirmed else "unknown",
        )

    if not quotes:
        return build_relation_candidate(
            name=name, direction_id=did, territory=territory, product=product,
            relation_class="rejected", reason=_REJECT_NO_EVIDENCE,
            limitations=["Нет фрагментов источников"],
        )
    return build_relation_candidate(
        name=name, direction_id=did, territory=territory, product=product,
        relation_class="candidate_for_check",
        reason="Доказательств пока недостаточно",
        quotes=quotes, territory_status="confirmed" if territory_confirmed else "unknown",
        limitations=limitations,
    )


def suppliers_from_directions(directions: list[dict[str, Any]]) -> list[str]:
    """Supplier/partner brand names declared in Stage A directions."""
    names: list[str] = []
    for d in directions or []:
        for b in d.get("brands") or []:
            rel = (b.get("relation") or "").lower()
            name = b.get("name") or ""
            if name and rel in {"supplier", "resale"}:
                names.append(name)
    return names


def rank_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order by proven match + source completeness (plan §3 step 6). Not a size ranking."""
    class_rank = {
        "direct_competitor": 0,
        "product_analog": 1,
        "supplier_partner": 2,
        "candidate_for_check": 3,
        "rejected": 4,
    }

    def key(row: dict[str, Any]):
        match = row.get("match") or {}
        score = class_rank.get(row.get("relation_class"), 5)
        completeness = (
            bool(row.get("evidence"))
            + bool(match.get("applications"))
            + bool(match.get("buyers"))
            + bool(row.get("links"))
        )
        return (score, -completeness, row.get("territory") != "russia")

    return sorted(rows, key=key)


def truncate_portfolio(rows: list[dict[str, Any]], *, max_ru: int = _MAX_RU, max_world: int = _MAX_WORLD) -> list[dict[str, Any]]:
    """Cap RF and world lists; keep rejected separately (not in the 7–10 goal)."""
    out: list[dict[str, Any]] = []
    ru = world = 0
    for row in rows:
        if row.get("relation_class") == "rejected":
            continue
        if row.get("territory") == "russia":
            if ru >= max_ru:
                continue
            ru += 1
        else:
            if world >= max_world:
                continue
            world += 1
        out.append(row)
    return out


# --- Search + verification pipeline ---------------------------------------------

async def discover_direction_candidates(
    company: dict[str, Any],
    directions: list[dict[str, Any]],
    *,
    llm=None,
    existing_evidence: list[dict[str, Any]] | None = None,
    query_budget: int = _MAX_QUERIES_TOTAL,
    budget=None,
) -> dict[str, Any]:
    """Search + classify candidates per direction. Returns table + states + stats.

    Extends the existing competitor-product-page flow with direction binding and
    relation classes. Directories/catalogs only discover candidates.
    """
    from osint_agent.market.evidence import _evidence_from_yandex
    from osint_agent.market.providers.web_search import YandexSearchProvider

    own_names = [
        str(company.get("name") or ""),
        str(company.get("full_name") or ""),
    ]
    # Short brand form of the studied company only (no hardcoded brands).
    _brand = re.sub(
        r"[^a-zа-яё0-9]", "",
        re.sub(r"\b(?:ооо|оао|зао|пао|ао|ип|llc|ltd|inc|gmbh)\b", " ",
               str(company.get("name") or "").lower()),
    )
    if len(_brand) >= 4:
        own_names.append(_brand)
    # Stage A brands with supplier/resale relation must not become competitors.
    supplier_names = suppliers_from_directions(directions)
    # also allow explicit supplier lists in company research
    for d in directions or []:
        supplier_names.extend(d.get("supplier_names") or [])
    supplier_names = list(dict.fromkeys(supplier_names))

    queries: list[dict[str, Any]] = []
    # Reserve world slots first so RF-only query packs cannot starve analogs.
    for d in directions or []:
        did = d.get("direction_id") or "d1"
        en_qs = direction_search_queries(d, lang="en")[:2]
        # Addressed world pass (plan §3 step 6 / §7): manufacturer brands, not directory chrome.
        cat_en = (d.get("product_category_en") or d.get("product_category_ru") or "")
        cat_en = re.sub(r"\s+", " ", str(cat_en).split("(")[0].strip())[:48]
        if not cat_en:
            continue
        en_qs = list(dict.fromkeys(en_qs + [
            f"{cat_en} brand manufacturer site",
            f"{cat_en} OEM producers Europe USA",
        ]))[:3]
        for q in en_qs:
            queries.append({"direction_id": did, "query": q, "region": "COM"})
        for q in direction_search_queries(d, lang="ru"):
            queries.append({"direction_id": did, "query": q, "region": "RU"})

    queries = queries[:query_budget]
    if budget is not None and hasattr(budget, "can_search"):
        # Cap by residual shared budget (Astra P2).
        allowed = budget.consume_search(len(queries), label="stage_b_queries")
        queries = queries[:allowed]
    search = YandexSearchProvider()
    states: list[dict[str, Any]] = []
    discovered: dict[str, list[dict[str, Any]]] = {}  # name_norm -> rows

    async def run_query(item: dict[str, Any]):
        try:
            page = await search.search(
                item["query"],
                filters={"region": "RU" if item.get("region") == "RU" else "COM"},
                budget=_SEARCH_BUDGET,
            )
            rows = _evidence_from_yandex(page.items, page.query or item["query"])
            for r in rows:
                r["direction_id"] = item.get("direction_id")
                r["search_region"] = item.get("region")
            return rows, {
                "source": "direction_competitor_search",
                "direction_id": item.get("direction_id"),
                "query": item["query"],
                "region": item.get("region"),
                "status": page.status.value,
                "count": len(rows),
                "message": page.message,
            }
        except Exception as exc:
            return [], {
                "source": "direction_competitor_search",
                "direction_id": item.get("direction_id"),
                "query": item["query"],
                "status": "error",
                "message": type(exc).__name__,
            }

    try:
        results = await asyncio.gather(*(run_query(q) for q in queries), return_exceptions=True)
    finally:
        await search.aclose()

    for result in results:
        if isinstance(result, Exception):
            states.append({"source": "direction_competitor_search", "status": "error",
                           "message": type(result).__name__})
            continue
        rows, state = result
        states.append(state)
        for row in rows:
            # extract company-ish names from titles/snippets
            for name in extract_candidate_names(row):
                key = normalize_company_key(name)
                if not key:
                    continue
                discovered.setdefault(key, {"name": name, "rows": [], "direction_ids": set()}).update(
                    name=name,
                )
                discovered[key]["rows"].append(row)
                if row.get("direction_id"):
                    discovered[key]["direction_ids"].add(row["direction_id"])

    # Also mine existing Stage A / market evidence for named companies.
    for row in existing_evidence or []:
        for name in extract_candidate_names(row):
            key = normalize_company_key(name)
            if not key:
                continue
            entry = discovered.setdefault(key, {"name": name, "rows": [], "direction_ids": set()})
            entry["rows"].append(row)
            entry["direction_ids"].add(row.get("direction_id") or (directions[0].get("direction_id") if directions else "d1"))

    # Classify each discovered company per its best direction.
    table: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    for key, entry in discovered.items():
        name = entry["name"]
        # Dedupe by short brand core: "КРПМС" and "ООО ПТК КРПМС" are one company.
        core = re.sub(
            r"[^a-zа-яё0-9]", "",
            re.sub(r"\b(?:ооо|оао|зао|пао|ао|ип|птк|тд|групп|group|ооо)\b", " ",
                   name.lower(), flags=re.I),
        )
        merge_key = core if len(core) >= 5 else key
        if merge_key in merged and len(name) < len(merged[merge_key]["name"]):
            # keep the longer official form
            pass
        bucket = merged.setdefault(merge_key, {"name": name, "rows": [], "direction_ids": set()})
        if len(name) > len(bucket["name"]):
            bucket["name"] = name
        bucket["rows"].extend(entry["rows"])
        bucket["direction_ids"] |= entry["direction_ids"]

    for merge_key, entry in merged.items():
        name = entry["name"]
        if _is_noise_name(name) or not is_plausible_company_name(name):
            continue
        # Atomic evidence: keep quote+url pairs from the same row (Astra P1).
        evidence_pairs: list[dict[str, Any]] = []
        for r in entry["rows"]:
            q = (r.get("quote") or r.get("passage") or "").strip()
            if not q:
                continue
            evidence_pairs.append({
                "quote": q[:400],
                "url": r.get("url"),
                "source_id": r.get("id") or r.get("source_id"),
                "title": r.get("title"),
            })
            if len(evidence_pairs) >= 6:
                break
        quotes = [p["quote"] for p in evidence_pairs]
        links = list(dict.fromkeys(p["url"] for p in evidence_pairs if p.get("url")))[:6]
        # Prefer the most company-like display name among aliases.
        aliases = [name] + list(entry.get("aliases") or [])
        name = max(aliases, key=lambda x: (
            bool(re.search(r"\b(ооо|llc|inc|gmbh|hydraulics|industries|технол)\b", x.lower())),
            len(x.split()),
            -abs(len(x) - 18),
        )) if aliases else name
        did_list = list(entry["direction_ids"]) or [d.get("direction_id") or "d1" for d in directions[:1]]
        # choose direction with most evidence overlap
        best_direction = directions[0] if directions else {"direction_id": "d1"}
        best_score = -1
        for d in directions or []:
            score = sum(1 for did in did_list if did == (d.get("direction_id") or ""))
            cat = (d.get("product_category_ru") or "").lower()
            if cat and any(w in " ".join(quotes).lower() for w in cat.split()[:2] if len(w) > 4):
                score += 1
            if score > best_score:
                best_score = score
                best_direction = d

        territory = "russia"
        ru_hits = sum(1 for r in entry["rows"] if r.get("search_region") != "COM")
        if ru_hits == 0 and entry["rows"]:
            territory = "world"
        # Prefer URL domain over search region when they disagree.
        host = ""
        if links:
            try:
                from urllib.parse import urlparse
                host = (urlparse(links[0]).hostname or "").lower()
            except Exception:
                host = ""
        if host.endswith(".ru") or host.endswith(".рф"):
            territory = "russia"
        elif host and not host.endswith(".ru") and territory == "world":
            territory = "world"

        product_overlap = detect_product_overlap(best_direction, quotes)
        role_compatible = detect_role_compatibility(best_direction, quotes)
        buyers_overlap = detect_buyers_overlap(best_direction, quotes)
        territory_confirmed = detect_territory(best_direction, quotes, territory)

        row = classify_candidate(
            name=name,
            direction=best_direction,
            own_company_names=own_names,
            supplier_or_partner_names=supplier_names,
            quotes=quotes,
            territory=territory,
            territory_confirmed=territory_confirmed,
            buyers_overlap=buyers_overlap,
            role_compatible=role_compatible,
            product_overlap=product_overlap,
        )
        row["links"] = links
        row["evidence"] = evidence_pairs[:4]
        row["direction_id"] = best_direction.get("direction_id") or row.get("direction_id")
        table.append(row)

    # After merge: drop names that are clearly not brand cores when a better alias exists.
    # Astra P1: do NOT merge different firms that share a catalog host.
    # Identity is name-based (already merged via normalize_company_key).
    table = rank_candidates(table)
    accepted = truncate_portfolio(table)
    rejected = [r for r in table if r.get("relation_class") == "rejected"]
    # one extra address pass note if short (plan §3 step 6)
    limitations: list[str] = []
    ru_accepted = sum(1 for r in accepted if r.get("territory") == "russia")
    world_accepted = sum(1 for r in accepted if r.get("territory") != "russia")
    if ru_accepted < 3 or world_accepted < 3:
        limitations.append(
            f"Короткий список: РФ={ru_accepted}, world={world_accepted}. "
            "Дополнительный адресный проход учтён в бюджете запросов; без ослабления проверок."
        )
    rate_limited = sum(1 for s in states if s.get("status") == "rate_limited")
    if rate_limited:
        limitations.append(f"Часть запросов rate_limited: {rate_limited}")
    if any(s.get("status") in {"error", "unavailable"} for s in states):
        limitations.append("Часть источников недоступна; частичный результат сохранён")

    return {
        "candidates_table": table,
        "accepted": accepted,
        "rejected": rejected,
        "by_class": {
            cls: sum(1 for r in accepted if r.get("relation_class") == cls)
            for cls in RELATION_CLASSES if cls != "rejected"
        },
        "source_states": states,
        "queries_used": queries,
        "limitations": limitations,
        "suppliers_excluded": supplier_names,
        "note": (
            "Порядок — релевантность совпадения продукции/применения/роли и полноты источников, "
            "не рейтинг размера бизнеса. Зарубежный аналог не обязан продавать в России; "
            "поставщик по одному направлению может быть конкурентом по другому."
        ),
    }


def _is_noise_name(value: str) -> bool:
    """Filter certificate codes, geo lists, marketplace chrome, product SKUs."""
    n = (value or "").strip()
    low = n.lower()
    if not n or len(n) < 3 or len(n) > 60:
        return True
    # certificate / SKU / version-like
    if re.match(r"^(?:ru|gost|iso|din|tu)\.?[a-z0-9.\-]+$", low):
        return True
    if re.match(r"^[a-z]{2,}\.[a-z0-9.\-]+$", low):
        return True
    if re.match(r"^[a-z]{1,5}\d{2,}[a-z0-9\-]*$", low):
        return True
    # SKU-like: letters + digits + optional suffix (БК 64011Е, BC 64011E)
    if re.match(r"^[A-Za-zА-Яа-я]{1,6}\s*\d{3,}[A-Za-zА-Яа-я0-9\-]*$", n):
        return True
    if re.match(r"^\d+([./]\d+)*$", n):
        return True
    # pure digits / years
    if re.match(r"^\d+([.,]\d+)*$", n):
        return True
    # title-case sentence starts that are not brand-like
    sentence_start = {
        "the", "our", "this", "that", "with", "from", "your", "when", "where",
        "best", "top", "pros", "wide", "various", "renowned", "expertise",
        "identify", "process", "compare", "browse", "request", "latest",
        "professional", "specialized", "recommended", "inventor", "distributor",
        "distributors", "companies", "company", "factory", "factories",
        "trading", "business", "china", "chinese", "made", "self", "non",
        "standard", "access", "international", "buyers", "equipment",
        "product", "products", "details", "price", "advantages", "distinct",
        "comparison", "identify", "hydraulic", "hydraulics", "hose", "hoses",
        "pressure", "high", "inner", "outer", "pipe", "manifold", "blocks",
        "cartridge", "valves", "valve", "check", "solenoid", "power", "pack",
        "cylinder", "system", "systems", "components", "leading", "world",
        "october", "profile", "overview", "target", "metoree", "saroit",
        "accio", "alibaba",
        "ru", "rf", "eu", "usa", "uk",
    }
    if low in sentence_start:
        return True
    words = [w.strip(".,;:!?") for w in low.split() if w]
    if all(w in sentence_start for w in words):
        return True
    # Directory/listicle titles: "Leading Hose Manufacturers", "Top Hydraulic ..."
    if words and words[0] in {
        "leading", "top", "best", "our", "the", "latest", "professional",
        "specialized", "recommended", "compare", "comparison", "choose", "select",
        "solutions", "solution", "custom", "european", "europe", "die",
        "these", "this", "that", "manifold", "manifolds", "hydraulic",
        "hydraulics", "high", "pressure", "power", "packs", "pack",
        "precision", "industrial", "industries", "about", "selected",
        "flexible", "fluid", "collaborative", "inspiring", "uncover",
        "research", "report", "segment", "strategic", "video", "assurance",
        "trade", "gold", "contact", "details", "to", "assist", "accio",
        "v-series", "series", "province", "city", "region",
        "choose", "your", "success", "panic", "various", "options", "available",
        "producing", "one", "onero", "custom", "global", "valve", "solutions",
        "modular", "rigging", "security", "struts", "south", "africa",
    }:
        return True
    # Geo phrases: "South Africa", "Rigging. EU"
    if words and words[0] in {"south", "north", "east", "west", "new", "greater"}:
        return True
    if any(w in {"manufacturer", "manufacturers", "vendors", "suppliers", "companies"} for w in words) \
            and not re.search(r"\b(ооо|llc|ltd|inc|gmbh|corp)\b", low) \
            and len(words) >= 3:
        # listicle phrase, not a legal/brand name
        return True
    # Country / region names
    if low in {
        "russia", "belarus", "kazakhstan", "azerbaijan", "armenia", "kyrgyzstan",
        "uzbekistan", "tajikistan", "moldova", "georgia", "ukraine", "china",
        "россия", "беларусь", "казахстан", "азербайджан", "армения", "кыргызстан",
    }:
        return True
    # Marketplace title dumps: "ООО X - 62 оригинальных товар(а)"
    if re.search(r"\s-\s+\d+\s", n) or "товар(а" in low or "оригинальн" in low:
        return True
    # Tagline fragments: "Hydraulic Manifold... Precision Hydraulic", "Compact. Leak-Free"
    if "..." in n or n.count(".") >= 2:
        return True
    if any(w in low for w in (
        "explore", "compact", "leak-free", "leak free", "high-pressure",
        "high pressure performance", "product details", "website",
        "trade assurance", "gold supplier", "contact details",
        "strategic", "collaborative", "inspiring", "uncover",
    )):
        return True
    if any(w in {"province", "city", "region", "district", "oblast"} for w in words):
        return True
    # Repeated token: "Hine Hine"
    raw_toks = [t.strip(".,;:!?") for t in n.split() if t]
    if len(raw_toks) >= 2 and len(set(t.lower() for t in raw_toks)) == 1:
        return True
    # Acronym + one word without industry/legal marker: "UHP Helix"
    # BUT allow "JSE Group", "PIX Robotics" (legal/industry second token).
    legal_or_industry = {
        "group", "llc", "ltd", "inc", "gmbh", "corp", "industries", "technologies",
        "robotics", "systems", "hydraulics", "engineering", "manufacturing", "hydro",
    }
    if (len(raw_toks) == 2 and raw_toks[0].isupper() and len(raw_toks[0]) <= 4
            and raw_toks[1].lower() not in legal_or_industry):
        return True
    if low in {"video. china", "video china", "china. the", "china. company"}:
        return True
    # Generic product tokens (plan §3 step 5: generic name ≠ company identity)
    if low in {"рвд", "rvg", "hose", "hoses", "тд", "td", "птк", "ооо", "оао", "зао"}:
        return True
    return False


def is_plausible_company_name(name: str) -> bool:
    """Company identity: legal form, brand+industry, or multi-token proper name."""
    n = re.sub(r"\s+", " ", (name or "").strip(" «»\"'.,;:("))
    if _is_noise_name(n):
        return False
    low = n.lower()
    if re.search(r"\b(ооо|оао|зао|пао|ао|ип|llc|ltd|inc|gmbh|corp|group|gmbh)\b", low):
        return True
    if re.search(r"\b(hydraulics|industries|technologies|manufacturing|engineering|systems|hydro)\b", low):
        return len(n.split()) >= 2
    # Multi-token Latin proper name: "Parker Hannifin", "Sun Hydraulics"
    tokens = n.split()
    if len(tokens) >= 2 and all(t[:1].isupper() or t[:1].isalpha() is False for t in tokens):
        if sum(1 for t in tokens if t[:1].isupper()) >= 2:
            return True
    # Strong single brand word (Gates, Graco, Hydroel): capitalized, 4+ letters
    if len(tokens) == 1 and len(n) >= 4 and n[0].isupper() and n.isalpha():
        return n.lower() not in sentence_start_words()
    # Two-token Latin with industry/tech suffix even if one word is short acronym
    if len(tokens) == 2 and tokens[0][:1].isupper() and tokens[1][:1].isupper():
        return True
    # Russian multiword proper names
    if len(tokens) >= 2 and any(t[:1].isupper() for t in tokens):
        return True
    return False


def sentence_start_words() -> set[str]:
    return {
        "production", "manufacture", "catalog", "company", "website", "profile",
        "overview", "leading", "manufacturer", "manufacturers", "hydraulics",
        "products", "suppliers", "comparison", "systems", "hose", "pressure",
    }


def extract_candidate_names(row: dict[str, Any]) -> list[str]:
    """Company-like names from search rows without inventing brands."""
    text = f"{row.get('title') or ''} {row.get('quote') or row.get('passage') or ''}"
    names: list[str] = []
    # «…» / "…" short brand-ish phrases
    for m in re.finditer(r"[«\"']([А-ЯA-Z][А-Яа-яЁёA-Za-z0-9&.\- ]{2,40})[»\"']", text):
        names.append(m.group(1).strip())
    # Legal-entity prefixes (RU)
    for m in re.finditer(
        r"\b(ООО|АО|ПАО|ЗАО|ОАО|ИП)\s+(?:[«\"']?([А-ЯA-Z][А-Яа-яЁёA-Za-z0-9&.\- ]{2,40}))",
        text,
    ):
        body = m.group(2) or ""
        if body:
            names.append(f"{m.group(1)} {body}")
            names.append(body)
    # Latin corporate names with legal/industry suffix
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9&.\-]{1,30}(?:\s+[A-Z][A-Za-z0-9&.\-]{1,30}){0,3})"
        r"(\s+(?:LLC|Ltd|Inc|GmbH|Corp|Corporation|Group|Hydraulics|Industries|"
        r"Manufacturing|Technologies|Engineering|Systems|Hydro))?\b",
        text,
    ):
        core = m.group(1).strip()
        suffix = (m.group(2) or "").strip()
        if suffix and suffix.lower() in {
            "hydraulics", "industries", "technologies", "manufacturing",
            "group", "engineering", "systems", "hydro",
        }:
            names.append(f"{core} {suffix}")
        elif suffix:
            names.append(core)
        elif re.match(r"^[A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){1,3}$", core):
            # multi-token CamelCase proper name only
            names.append(core)

    cleaned: list[str] = []
    for n in names:
        n = re.sub(r"\s+", " ", n).strip(" «»\"'.,;:(")
        if not is_plausible_company_name(n):
            continue
        # product-card titles: keep leading brand only
        if re.search(r"\b(блок клапанов|каталог|аналоги|скачать|цена)\b", n.lower()):
            head = " ".join(n.split()[:2]).strip()
            if is_plausible_company_name(head):
                cleaned.append(head)
            continue
        cleaned.append(n)
    return list(dict.fromkeys(cleaned))[:6]


def detect_product_overlap(direction: dict[str, Any], quotes: list[str]) -> bool:
    """Product overlap in RU and EN — require multi-token category match.

    P1 (Astra): one long word (or hydraulic+hoses vs hydraulic+pumps) is NOT enough.
    """
    cat_ru = (direction.get("product_category_ru") or "").lower()
    cat_en = (direction.get("product_category_en") or "").lower()
    ru_words = [w for w in re.findall(r"[a-zа-яё]{4,}", cat_ru)]
    en_words = [w for w in re.findall(r"[a-z]{4,}", cat_en)]
    blob = " ".join(quotes).lower()
    if not ru_words and not en_words:
        return False

    def _score(words: list[str]) -> int:
        hits = 0
        for w in words:
            if w in blob:
                hits += 1
                continue
            # light stemming: «шланги» ~ «шлангов», «гидравлические» ~ «гидравлических»
            stem = w[: max(5, len(w) - 3)]
            if len(stem) >= 5 and stem in blob:
                hits += 1
        return hits

    ru_hits = _score(ru_words) if ru_words else 0
    en_hits = _score(en_words) if en_words else 0
    # Need majority of category tokens (at least 2 when available).
    if ru_words and ru_hits >= max(2, (len(ru_words) + 1) // 2):
        return True
    if en_words and en_hits >= max(2, (len(en_words) + 1) // 2):
        return True
    # Two-word EN category as phrase (hoses + hydraulic both present is still ok
    # only if the distinctive noun is present).
    if len(en_words) >= 2 and all(w in blob for w in en_words):
        return True
    if len(ru_words) >= 2 and all(w in blob for w in ru_words):
        return True
    return False


def detect_role_compatibility(direction: dict[str, Any], quotes: list[str]) -> bool | None:
    role = direction.get("role") or "unknown"
    blob = " ".join(quotes).lower()
    if role == "manufacturer":
        return bool(re.search(
            r"производ|изготов|manufactur|produce[sd]?|factory|завод|OEM",
            blob, re.I,
        ))
    if role == "distributor":
        return bool(re.search(
            r"дистрибьютор|дилер|постав|supplier|distributor|dealer|resale|wholesale",
            blob, re.I,
        ))
    if role == "integrator":
        return bool(re.search(
            r"интегр|сборк|внедрен|integration|systems? integration|комплексн",
            blob, re.I,
        ))
    if role == "service_provider":
        return bool(re.search(r"услуг|сервис|монтаж|service|repair", blob, re.I))
    return None


def detect_buyers_overlap(direction: dict[str, Any], quotes: list[str]) -> bool | None:
    buyers = [b.lower() for b in direction.get("buyer_segments") or [] if b]
    apps = [a.lower() for a in direction.get("applications") or [] if a]
    blob = " ".join(quotes).lower()
    if not buyers and not apps:
        return None
    hits = 0
    for phrase in (buyers + apps):
        tokens = [t for t in re.findall(r"[a-zа-яё]{4,}", phrase)]
        if tokens and sum(1 for t in tokens if t in blob) >= max(1, len(tokens) // 2):
            hits += 1
    if hits >= 2:
        return True
    if hits == 1:
        return True
    return False if (buyers or apps) else None


def detect_territory(
    direction: dict[str, Any], quotes: list[str], default_territory: str,
) -> bool | None:
    """territory_confirmed: True if RF presence claimed, False if explicitly foreign-only."""
    blob = " ".join(quotes).lower()
    ru_markers = ("росси", "рф", "москв", "санкт-петербург", "петербург", "московск", "russia", "russian")
    foreign_only = ("germany", "deutschland", "italia", "italy", "usa", "united states", "кнр", "china")
    if any(m in blob for m in ru_markers):
        return True
    if default_territory == "world" and any(m in blob for m in foreign_only):
        return False
    return None
