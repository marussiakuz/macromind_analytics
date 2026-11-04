"""Automatic market analysis from registry evidence — evidence-first (spec Task1 §3–4).

False claims removed:
- related orgs ≠ competitors (typed relations only);
- OKVED ≠ product;
- procurement sum ≠ market size;
- model claims need concrete evidence_ids (no blanket fill).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _norm_name(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


# --- typed relations (F01–F04) ------------------------------------------------

def _add_relation(
    store: dict[str, dict[str, Any]],
    *,
    name: str,
    inn: str | None,
    role: str,
    evidence_id: str,
    note: str,
) -> None:
    name = _norm_name(name)
    if not name:
        return
    key = f"inn:{inn}" if inn else f"name:{name}"
    row = store.setdefault(
        key,
        {
            "name": name,
            "inn": inn,
            "roles": [],
            "evidence_ids": [],
            "notes": [],
            "confidence": "low" if not inn else "medium",
        },
    )
    if role not in row["roles"]:
        row["roles"].append(role)
    if evidence_id not in row["evidence_ids"]:
        row["evidence_ids"].append(evidence_id)
    if note not in row["notes"]:
        row["notes"].append(note)


def _extract_legal_relations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(items):
        eid = f"legal-cases:{row.get('id') or i}"
        fields = row.get("fields") or {}
        # структурированные строки; не резать по запятым в названии (F04)
        for label, role in (("Истцы", "истец"), ("Ответчики", "ответчик")):
            raw = fields.get(label)
            if not raw:
                continue
            # список приходит строкой "Наим; ИНН" — берём целиком как одну сторону
            party = _norm_name(str(raw))
            if not party or len(party) < 3:
                continue
            _add_relation(
                store,
                name=party,
                inn=None,
                role=role,
                evidence_id=eid,
                note="сторона арбитражного дела; предмет спора не проверен",
            )
    return list(store.values())


def _extract_contract_relations(items: list[dict[str, Any]]) -> dict[str, Any]:
    store: dict[str, dict[str, Any]] = {}
    total = Decimal(0)
    priced = 0
    for i, row in enumerate(items):
        eid = f"contracts:{row.get('id') or i}"
        fields = row.get("fields") or {}
        buyer = _norm_name(str(fields.get("Заказчик") or ""))
        suppliers_raw = fields.get("Поставщики")
        # поставщики — одна строка; не резать по запятым в названии
        supplier = _norm_name(str(suppliers_raw)) if suppliers_raw else ""
        if buyer:
            _add_relation(store, name=buyer, inn=None, role="заказчик", evidence_id=eid, note="участник закупки")
        if supplier:
            _add_relation(store, name=supplier, inn=None, role="поставщик", evidence_id=eid, note="участник закупки")
        amount = _dec(row.get("amount"))
        if amount is not None:
            total += amount
            priced += 1
    return {
        "relations": list(store.values()),
        "contract_count": len(items),
        "priced_contracts": priced,
        "observed_procurement_value": format(total, "f") if priced else None,
    }


def _pick_latest_financial_year(finances: dict[str, Any] | None) -> dict[str, Any] | None:
    years = (finances or {}).get("years") or []
    best = None
    best_year = None
    for y in years:
        year = y.get("year")
        try:
            yi = int(year)
        except (TypeError, ValueError):
            continue
        if y.get("revenue") is None and y.get("net_profit") is None:
            continue
        if best_year is None or yi > best_year:
            best_year = yi
            best = y
    return best


def _margin(last_year: dict[str, Any] | None) -> dict[str, Any] | None:
    """Рентабельность = прибыль / выручка × 100% за один год (spec §4)."""
    if not last_year:
        return None
    rev = _dec(last_year.get("revenue"))
    profit = _dec(last_year.get("net_profit"))
    if rev is None or rev == 0:
        return {"status": "not_calculated", "reason": "Нет выручки за тот же период"}
    if profit is None:
        return {"status": "not_calculated", "reason": "Нет чистой прибыли за тот же период"}
    pct = (profit / rev) * Decimal(100)
    return {
        "status": "computed",
        "year": last_year.get("year"),
        "margin_pct": format(pct.quantize(Decimal("0.01")), "f"),
        "revenue": format(rev, "f"),
        "net_profit": format(profit, "f"),
        "formula": "net_profit / revenue * 100",
    }


def build_auto_analysis(
    company: dict[str, Any] | None,
    finances: dict[str, Any] | None = None,
    registries: dict[str, Any] | None = None,
    *,
    site_text: str | None = None,
    extra_sources: list[str] | None = None,
) -> dict[str, Any]:
    registries = registries or {}
    company = company or {}
    inn = company.get("inn")

    okved = company.get("okved_main")
    # OKVED ≠ product (F05): product confirmed only from site/registry texts
    product = company.get("product") or company.get("product_name")
    buyer = company.get("buyer") or company.get("customer")
    product_status = "confirmed" if product else "needs_clarification"
    buyer_status = "confirmed" if buyer else "needs_clarification"
    directions: list[dict[str, Any]] = []
    okved_desc = company.get("okved_description")

    if site_text or extra_sources or company.get("products") or (company.get("contacts") or {}).get("ВебСайт"):
        try:
            from osint_agent.market.company_profile import (
                build_company_profile,
                extract_directions_from_text,
            )
            profile = build_company_profile(
                company, site_text=site_text, extra_sources=extra_sources
            )
            if profile.directions and not product:
                directions = [
                    {
                        "name": d.name,
                        "status": d.status,
                        "buyers": d.buyers,
                        "applications": d.applications,
                        "source": d.source,
                        "confidence": d.confidence,
                    }
                    for d in profile.directions
                ]
                product = profile.directions[0].name
                product_status = "needs_clarification" if profile.multi_product else "inferred_from_source"
                if profile.directions[0].buyers and not buyer:
                    buyer = profile.directions[0].buyers[0]
                    buyer_status = "inferred_from_source"
            company_profile_extra = profile.to_dict()
        except Exception:  # noqa: BLE001
            company_profile_extra = {}
    else:
        company_profile_extra = {}

    product_scope = {
        "product": product,
        "product_status": product_status,
        "buyer": buyer,
        "buyer_status": buyer_status,
        "okved": okved,
        "okved_description": company.get("okved_description"),
        "countries": ["RU"],
        "reference_period": None,
        "measure_type": "revenue",
        "directions": directions,
        "multi_product": len(directions) > 1,
        "official_site": company_profile_extra.get("official_site"),
        "site_status": company_profile_extra.get("site_status"),
        "note": (
            "Продукт и покупатель требуют уточнения. ОКВЭД — зарегистрированный вид деятельности."
            if product_status == "needs_clarification"
            else "Формулировка продукта из доступных источников; требует подтверждения аналитиком."
        ),
    }

    # Судебные дела и производства НЕ используются для оценки рынка и конкурентов
    # (по ним нельзя оценить продукт/покупателя/долю рынка).
    contract_items = (registries.get("contracts") or {}).get("items") or []
    contract_pack = _extract_contract_relations(contract_items)

    # исключить саму компанию из связей (F01)
    def _is_self(name: str) -> bool:
        self_names = {
            _norm_name(company.get("name")),
            _norm_name(company.get("full_name")),
        }
        return _norm_name(name) in self_names and bool(_norm_name(name))

    # только закупочные связи — не истцы/ответчики из судов
    all_rels = [
        r for r in contract_pack["relations"]
        if not _is_self(r["name"])
    ]

    # конкуренты НЕ подтверждены автоматически (spec §3.1)
    competitor_candidates = [
        {
            "name": r["name"],
            "status": "candidate_for_check",
            "roles": r["roles"],
            "evidence_ids": r["evidence_ids"],
            "reason": "Связь из закупок; продукт и покупатель не подтверждены",
        }
        for r in all_rels
        if "заказчик" in r["roles"] or "поставщик" in r["roles"]
    ]
    confirmed_competitors: list[dict[str, Any]] = []

    # судебные/исполнительные производства — только для карточки надёжности,
    # НЕ в рыночный summary
    legal_events: list[dict[str, Any]] = []

    last_year = _pick_latest_financial_year(finances)
    margin = _margin(last_year)

    procurement = {
        "observed_procurement_value": contract_pack["observed_procurement_value"],
        "label": "Сумма контрактов в доступной выборке",
        "contract_count": contract_pack["contract_count"],
        "priced_contracts": contract_pack["priced_contracts"],
        "is_tam": False,
        "note": "Не является размером рынка или оценкой сверху вниз (F11)",
    }

    limitations = [
        "Продукт и покупатель требуют уточнения — ОКВЭД их не определяет.",
        "Связи из закупок — не подтверждённые конкуренты (нужно сходство продукта и покупателей).",
        "Сумма контрактов в выборке ≠ TAM.",
        "Судебные дела и производства не используются для оценки рынка и конкурентов.",
    ]

    evidence_refs = []
    for r in all_rels[:20]:
        evidence_refs.append(
            {
                "id": r["evidence_ids"][0] if r["evidence_ids"] else f"rel:{r['name']}",
                "type": "registry_relation",
                "name": r["name"],
                "roles": r["roles"],
                "confidence": r["confidence"],
            }
        )
    if procurement["observed_procurement_value"]:
        evidence_refs.append(
            {
                "id": "procurement_sum",
                "type": "observed_procurement_value",
                "value": procurement["observed_procurement_value"],
            }
        )

    return {
        "study_id": None,
        "report_version": None,
        "binding_revision": None,
        "legal_entity_inn": inn,
        "product_scope": product_scope,
        "market_scope": product_scope,
        "reference_period": None,
        "as_of": _now(),
        "estimates_rf": None,  # F11: закупки не в estimates
        "estimates_world": None,
        "triangulation_status": "insufficient_data",
        "observed_procurement": procurement,
        "related_organizations": all_rels,
        "competitor_candidates": competitor_candidates,
        "confirmed_competitors": confirmed_competitors,
        "competitor_findings": [],  # пусто = нехватка сведений, не «конкурентов нет»
        "competitor_status": "insufficient_data",
        "legal_events": legal_events,
        "finance_summary": {
            "latest_year": last_year,
            "margin": margin,
            "note": "Год выбран численно максимальным (F08)",
        },
        "technology_findings": [],
        "limitations": limitations,
        "data_completeness": {
            "has_top_down": False,
            "has_bottom_up": False,
            "has_triangulation": False,
            "has_product_confirmed": False,
            "has_confirmed_competitors": False,
            # судебные/исполнительные производства не входят в рыночную оценку
            "registry_sections": {
                "contracts": contract_pack["contract_count"],
                "inspections": len((registries.get("inspections") or {}).get("items") or []),
                "fedresurs": len((registries.get("fedresurs") or {}).get("items") or []),
                "bankruptcy": len((registries.get("bankruptcy") or {}).get("items") or []),
            },
            "excluded_from_market": ["legal_cases", "enforcements"],
            "last_revenue": None if not last_year else {
                "year": last_year.get("year"),
                "revenue": last_year.get("revenue"),
                "net_profit": last_year.get("net_profit"),
            },
        },
        "review_status": "auto_draft",
        "freshness": _now(),
        "evidence_refs": evidence_refs,
        "auto": True,
    }


# --- Qwen contract (spec §6): no blank evidence fill (F13) --------------------

FORBIDDEN_CLAIM_HINTS = (
    "агрессивн",
    "взыскан",  # без предмета дела
    "качество клиент",
    "устойчивост спрос",
    "рынок равен",
    "конкурентов нет",
)

# «999 млрд», «12,5 млн руб», «18%», «1 250 000»
_NUM_RE = re.compile(
    r"(?<![\w,])(\d[\d\s]*[.,]?\d*)\s*"
    r"(млрд|млн|тыс|трлн|%)?",
    re.IGNORECASE,
)

_SCALE = {
    "тыс": 1_000,
    "млн": 1_000_000,
    "млрд": 1_000_000_000,
    "трлн": 1_000_000_000_000,
    "%": 1,
}


def _norm_number(raw: str, scale: str | None) -> Decimal | None:
    cleaned = re.sub(r"\s+", "", raw).replace(",", ".")
    val = _dec(cleaned)
    if val is None:
        return None
    if scale:
        val = val * _SCALE.get(scale.lower(), 1)
    return val


def extract_numbers(text: str) -> list[Decimal]:
    """All numeric literals in text, scales (млн/млрд) applied."""
    out: list[Decimal] = []
    for m in _NUM_RE.finditer(text or ""):
        num = _norm_number(m.group(1), m.group(2))
        if num is not None:
            out.append(num)
    return out


def _evidence_numbers(evidence: dict[str, Any]) -> list[Decimal]:
    nums: list[Decimal] = []
    for key in ("statement", "quote", "value", "revenue", "net_profit", "amount", "text"):
        v = evidence.get(key)
        if v is None or v == "":
            continue
        if isinstance(v, (int, float, Decimal)):
            d = _dec(v)
            if d is not None:
                nums.append(d)
        else:
            nums.extend(extract_numbers(str(v)))
    for nested in ("fields", "fact", "metrics"):
        block = evidence.get(nested)
        if isinstance(block, dict):
            for v in block.values():
                if isinstance(v, (int, float, Decimal)):
                    d = _dec(v)
                    if d is not None:
                        nums.append(d)
                elif isinstance(v, str):
                    nums.extend(extract_numbers(v))
    return nums


def _numbers_match(claimed: Decimal, available: list[Decimal], *, rel_tol: str = "0.01") -> bool:
    tol = Decimal(rel_tol)
    for a in available:
        if claimed == 0 and a == 0:
            return True
        denom = abs(claimed) if abs(claimed) > abs(a) else abs(a)
        if denom == 0:
            continue
        if abs(claimed - a) / denom <= tol:
            return True
    return False


def _structured_fact_ok(raw: dict[str, Any], evidence_list: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Facts with company/metric/value must match evidence content (Astra P1)."""
    problems: list[str] = []
    fact = raw.get("fact") if isinstance(raw.get("fact"), dict) else None
    if not fact:
        return True, problems
    for required in ("company", "metric", "value"):
        if not fact.get(required) and fact.get(required) != 0:
            problems.append(f"fact_missing_{required}")
    val = _dec(fact.get("value"))
    if val is not None:
        available: list[Decimal] = []
        for ev in evidence_list:
            available.extend(_evidence_numbers(ev))
        if available and not _numbers_match(val, available):
            problems.append("fact_value_not_in_evidence")
    period = fact.get("period")
    if period:
        period_s = str(period)
        blob = " ".join(
            str(ev.get("statement") or "") + " " + str(ev.get("quote") or "") + " " + str(ev.get("period") or "")
            for ev in evidence_list
        )
        if period_s not in blob and period_s[:4] not in blob:
            problems.append("fact_period_not_in_evidence")
    return not problems, problems


def validate_llm_claims(
    claims: list[dict[str, Any]],
    evidence_ids: set[str],
    calculations: set[str] | None = None,
    evidence_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Возвращает (accepted, rejected).

    ID доказательства не подтверждает число (Astra P1): если в утверждении есть
    цифры, хотя бы одна должна совпасть с содержанием привязанных evidence
    (или с расчётом). Пустые/чужие evidence_id отклоняются.
    """
    calculations = calculations or set()
    evidence_by_id = evidence_by_id or {}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(claims, list):
        return [], [{"reason": "claims_not_a_list"}]
    for raw in claims or []:
        if not isinstance(raw, dict):
            rejected.append({"reason": "not_an_object", "raw": str(raw)[:80]})
            continue
        if (not isinstance(raw.get("statement"), str)
                or any(not isinstance(raw.get(key, []), list)
                       or any(not isinstance(item, str) for item in raw.get(key, []))
                       for key in ("evidence_ids", "calculation_ids", "limitations"))):
            rejected.append({"reason": "invalid_claim_fields"})
            continue
        if raw.get("claim_type", "interpretation") not in {
            "interpretation", "fact", "forecast", "team_claim", "calculation",
        }:
            rejected.append({"reason": "invalid_claim_type"})
            continue
        statement = raw["statement"]
        ids = [str(x) for x in (raw.get("evidence_ids") or []) if x]
        calc_ids = [str(x) for x in (raw.get("calculation_ids") or []) if x]
        problems: list[str] = []
        if not statement.strip():
            problems.append("empty_statement")
        # F13: каждая ссылка должна существовать; общие не подставляются
        if not ids and not calc_ids:
            problems.append("missing_evidence")
        for eid in ids:
            if eid not in evidence_ids:
                problems.append(f"unknown_evidence:{eid}")
        for cid in calc_ids:
            if cid not in calculations:
                problems.append(f"unknown_calculation:{cid}")

        linked = [evidence_by_id[eid] for eid in ids if eid in evidence_by_id]

        # Astra P1: существующий ID с чужим числом не проходит как факт
        claimed_nums = extract_numbers(statement)
        if claimed_nums and (linked or calc_ids):
            available: list[Decimal] = []
            for ev in linked:
                available.extend(_evidence_numbers(ev))
            if calc_ids and not available:
                # calculation-backed claims: cannot auto-verify content here
                pass
            elif available:
                if not any(_numbers_match(n, available) for n in claimed_nums):
                    problems.append("numbers_not_in_evidence")
            elif linked == [] and calc_ids:
                pass
            elif claimed_nums and not available and linked:
                problems.append("numbers_not_in_evidence")

        ok_fact, fact_problems = _structured_fact_ok(raw, linked)
        problems.extend(fact_problems)

        # F06/F07: смысловые запреты
        low = statement.lower()
        if "агрессивн" in low:
            problems.append("unsupported_legal_interpretation")
        if "качеств" in low and "клиент" in low and "подтвержд" not in low:
            problems.append("unsupported_causal_claim")
        if "конкурент" in low and "подтвержд" not in low and raw.get("claim_type") == "fact":
            problems.append("unconfirmed_competitor_as_fact")

        claim = {
            "section": raw.get("section") or "russian_market",
            "statement": statement,
            "claim_type": raw.get("claim_type") or "interpretation",
            "evidence_ids": ids,
            "calculation_ids": calc_ids,
            "limitations": list(raw.get("limitations") or []) + (
                [] if ids or calc_ids else ["Нет конкретного доказательства"]
            ),
            # Citation existence does not verify meaning. Only a separate review
            # may promote this status; never accept the model's self-attestation.
            "verification_status": "needs_review",
        }
        if raw.get("fact"):
            claim["fact"] = raw["fact"]
        if problems:
            claim["reject_reasons"] = problems
            rejected.append(claim)
        else:
            accepted.append(claim)
    return accepted, rejected


def build_summary_from_accepted(accepted: list[dict[str, Any]]) -> tuple[str, list[str]]:
    """F14: summary/risks только из принятых утверждений."""
    if not accepted:
        return "Нет допустимых выводов — требуются доказательства.", []
    summary = " ".join(c["statement"] for c in accepted[:3])
    risks = [
        c["statement"]
        for c in accepted
        if "risk" in c.get("section", "").lower() or "риск" in c["statement"].lower()
    ]
    return summary[:400], risks[:5]


def refuse_if_insufficient(summary: dict[str, Any], *, min_facts: int = 1) -> dict[str, Any]:
    """Independent of fund specialization (2026-10-22).

    If evidence/calculate inputs are missing, refuse to publish a quantitative
    conclusion instead of filling blanks. Always available for chemistry,
    logistics, RPA, etc.
    """
    ev = summary.get("evidence_refs") or []
    fin = summary.get("finance_summary") or {}
    data = summary.get("data_completeness") or {}
    problems: list[str] = []

    if len(ev) < min_facts:
        problems.append("insufficient_evidence")
    if not fin.get("latest_year") and not summary.get("observed_procurement", {}).get("observed_procurement_value"):
        problems.append("no_quantitative_inputs")
    if summary.get("triangulation_status") == "insufficient_data":
        problems.append("no_triangulation")
    if data.get("has_confirmed_competitors") is False and summary.get("competitor_status") == "insufficient_data":
        problems.append("competitors_unconfirmed")

    if problems:
        summary = dict(summary)
        summary["analysis_status"] = "insufficient_data"
        summary["refusal_reasons"] = problems
        summary["llm_summary"] = (
            "Недостаточно проверенных данных для количественного вывода. "
            "Требуются доказательства: " + ", ".join(problems) + "."
        )
        summary["llm_interpretation"] = summary.get("llm_interpretation") or []
        summary.setdefault("limitations", []).append("auto_refused_insufficient_data")
        return summary
    summary = dict(summary)
    summary.setdefault("analysis_status", "ok")
    return summary


def select_evidence_for_claims(
    accepted: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Only concrete evidence_ids from accepted claims (never blanket refs)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in accepted or []:
        for eid in claim.get("evidence_ids") or []:
            if eid in seen:
                continue
            seen.add(eid)
            row = evidence_by_id.get(eid)
            if row:
                out.append(row)
    return out


async def add_llm_interpretation(summary: dict[str, Any], llm=None) -> dict[str, Any]:
    """Qwen only after evidence validation (spec §6, F13–F15)."""
    from osint_agent.market.providers.yandex_llm import (
        INTERPRETATION_SYSTEM,
        parse_interpretation,
    )
    from osint_agent.market.providers.factory import get_llm_client

    def _clip_evidence(rows):
        clipped = []
        for e in (rows or [])[:20]:
            row = dict(e)
            for field in ("quote", "abstract"):
                if isinstance(row.get(field), str):
                    row[field] = row[field][:500]
            clipped.append(row)
        return clipped

    evidence_ids = {str(e.get("id")) for e in (summary.get("evidence_refs") or []) if isinstance(e, dict)}
    evidence_by_id = {
        str(e.get("id")): e
        for e in (summary.get("evidence_refs") or [])
        if isinstance(e, dict) and e.get("id")
    }
    client = llm or get_llm_client()
    try:
        result = await client.complete(
            INTERPRETATION_SYSTEM,
            {
                "study_id": summary.get("study_id"),
                "company": {
                    "inn": summary.get("legal_entity_inn"),
                    "product_scope": summary.get("product_scope"),
                },
                "evidence": _clip_evidence(summary.get("evidence_refs")),
                "calculations": summary.get("finance_summary"),
                "facts": {
                    "related_organizations": summary.get("related_organizations"),
                    "legal_events": summary.get("legal_events"),
                    "observed_procurement": summary.get("observed_procurement"),
                    "limitations": summary.get("limitations"),
                },
            },
        )
    finally:
        close = getattr(client, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass

    summary["llm_model"] = getattr(client, "settings", None) and client.settings.model_uri
    if not result.ok:
        summary["llm_status"] = result.error_code or "error"
        summary["llm_error"] = result.error
        summary["llm_interpretation"] = []
        summary["llm_rejected_claims"] = []
        return summary

    parsed = parse_interpretation(result.text)
    if not parsed:
        summary["llm_status"] = "bad_response"
        summary["llm_error"] = "Не удалось разобрать JSON интерпретации"
        summary["llm_interpretation"] = []
        summary["llm_rejected_claims"] = []
        return summary

    accepted, rejected = validate_llm_claims(
        parsed.get("interpretation") or [], evidence_ids, evidence_by_id=evidence_by_id
    )
    summary_text, risks = build_summary_from_accepted(accepted)
    summary["llm_status"] = "ok"
    summary["llm_error"] = None
    summary["llm_interpretation"] = accepted
    summary["llm_rejected_claims"] = rejected
    summary["llm_summary"] = summary_text  # F14: только из принятых
    summary["llm_risks"] = risks  # F15
    summary["llm_questions"] = parsed.get("questions") or []
    summary["llm_prompt_version"] = "interpretation/0.2"
    # Fund-independent refusal when inputs are too thin (chemistry, RPA, …)
    return refuse_if_insufficient(summary)


async def attach_external_evidence(summary: dict[str, Any], collect=None) -> dict[str, Any]:
    """Stage C: подключить Yandex/OpenAlex фактуру к сводке (F16–F20)."""
    from osint_agent.market.evidence import collect_market_evidence, market_estimates_from_evidence

    collector = collect or (lambda company: collect_market_evidence(company))
    company = {
        "inn": summary.get("legal_entity_inn"),
        "name": (summary.get("product_scope") or {}).get("okved_description")
        or (summary.get("product_scope") or {}).get("product"),
        "okved_description": (summary.get("product_scope") or {}).get("okved_description"),
        "okved_main": (summary.get("product_scope") or {}).get("okved"),
    }
    try:
        pack = await collector(company)
    except Exception as exc:
        summary["external_source_states"] = [{"source": "collector", "status": "error", "message": str(exc)[:200]}]
        summary["limitations"] = list(summary.get("limitations") or []) + ["Сбор внешней фактуры не выполнен"]
        return summary

    summary["external_source_states"] = pack.get("source_states") or []
    summary["external_evidence"] = pack.get("evidence") or []
    summary["market_estimates_from_snippets"] = market_estimates_from_evidence(pack.get("evidence") or [])
    extra = list(pack.get("limitations") or [])
    summary["limitations"] = list(summary.get("limitations") or []) + extra
    # evidence_refs: OpenAlex/Yandex content must be available for claim checks
    refs = list(summary.get("evidence_refs") or [])
    seen_ids = {str(r.get("id")) for r in refs if isinstance(r, dict)}
    for e in summary["external_evidence"]:
        eid = str(e.get("id"))
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        refs.append({
            "id": e.get("id"),
            "type": e.get("type"),
            "name": e.get("title"),
            "url": e.get("url"),
            # full content for validate_llm_claims number matching
            "statement": e.get("quote") or e.get("title"),
            "quote": e.get("quote"),
            "source": e.get("source_id"),
            "read_level": (
                "full_text" if e.get("full_text_read")
                else "abstract_only" if e.get("quote") and e.get("type") == "scientific_work"
                else "snippet_only"
            ),
            "doi": e.get("doi"),
            "authors": e.get("authors"),
            "publication_date": e.get("publication_date"),
            "completeness": e.get("completeness"),
        })
    summary["evidence_refs"] = refs
    return summary


async def add_llm_interpretation_cached(summary: dict[str, Any], llm=None) -> dict[str, Any]:
    """Кэш + лимиты + учёт расходов (Stage D, F32–F34)."""
    from osint_agent.market.llm_cache import (
        cache_key,
        shared_budget,
        shared_cache,
        shared_ledger,
    )
    from osint_agent.market.providers.yandex_llm import INTERPRETATION_SYSTEM

    def _clip_evidence(rows):
        clipped = []
        for e in (rows or [])[:20]:
            row = dict(e)
            for field in ("quote", "abstract"):
                if isinstance(row.get(field), str):
                    row[field] = row[field][:500]
            clipped.append(row)
        return clipped

    evidence_ids = {str(e.get("id")) for e in (summary.get("evidence_refs") or []) if isinstance(e, dict)}
    evidence_by_id = {
        str(e.get("id")): e
        for e in (summary.get("evidence_refs") or [])
        if isinstance(e, dict) and e.get("id")
    }
    payload = {
        "company": {
            "inn": summary.get("legal_entity_inn"),
            "product_scope": summary.get("product_scope"),
        },
        "evidence": _clip_evidence(summary.get("evidence_refs")),
        "facts": {
            "related_organizations": summary.get("related_organizations"),
            "legal_events": summary.get("legal_events"),
            "observed_procurement": summary.get("observed_procurement"),
        },
    }
    model = "yandex-studio/qwen"
    from osint_agent.knowledge.cache_keys import cache_key_with_corpus, corpus_snapshot_id
    evidence_ids = [str(e.get("id")) for e in (summary.get("evidence_refs") or []) if isinstance(e, dict)]
    # §6.5 p.4: cache key includes corpus snapshot so A/B variants never share answers
    key = cache_key_with_corpus(
        model=model,
        prompt_version="interpretation/0.2",
        system=INTERPRETATION_SYSTEM,
        payload=payload,
        workspace_id=summary.get("workspace_id"),
        document_ids=evidence_ids,
    )
    summary["corpus_snapshot"] = corpus_snapshot_id(
        workspace_id=summary.get("workspace_id"), document_ids=evidence_ids
    )
    cache = shared_cache()
    hit = cache.get(key)
    if hit:
        parsed = __import__("osint_agent.market.providers.yandex_llm", fromlist=["parse_interpretation"]).parse_interpretation(hit.text)
        if parsed is None:
            # ошибочный кэш не считаем успехом
            pass
        else:
            accepted, rejected = validate_llm_claims(
                parsed.get("interpretation") or [], evidence_ids, evidence_by_id=evidence_by_id
            )
            summary_text, risks = build_summary_from_accepted(accepted)
            summary.update({
                "llm_status": "ok",
                "llm_error": None,
                "llm_interpretation": accepted,
                "llm_rejected_claims": rejected,
                "llm_summary": summary_text,
                "llm_risks": risks,
                "llm_questions": parsed.get("questions") or [],
                "llm_prompt_version": "interpretation/0.2",
                "llm_cache_hit": True,
            })
            return summary

    inflight = cache.coalesce(key)
    if inflight is not None:
        # F32: ждём уже идущий такой же запрос
        wait_hit = await cache.wait_inflight_async(key)
        if wait_hit:
            summary["llm_cache_hit"] = True
            summary["llm_coalesced"] = True
            return await add_llm_interpretation_cached(summary, llm=llm)
        # We do not own the in-flight entry. Never issue a duplicate call or
        # release another request's entry after a timeout/failure.
        summary.update({"llm_status": "pending_or_failed",
                        "llm_error": "Предыдущий запрос ещё выполняется или завершился без результата",
                        "llm_interpretation": [], "llm_rejected_claims": []})
        return summary

    budget = shared_budget()
    ok, reason = budget.try_acquire()
    if not ok:
        cache.release(key)
        summary["llm_status"] = "limit_reached"
        summary["llm_error"] = reason or "Лимит обращений исчерпан"
        summary["llm_interpretation"] = []
        summary["llm_rejected_claims"] = []
        return summary

    accounted = False
    try:
        out = await add_llm_interpretation(summary, llm=llm)
        ledger = shared_ledger()
        if out.get("llm_status") == "ok":
            # успех кэшируем (F33: ключ включает evidence)
            text = json.dumps({
                "interpretation": out.get("llm_interpretation") or [],
                "summary": out.get("llm_summary") or "",
                "risks": out.get("llm_risks") or [],
                "questions": out.get("llm_questions") or [],
            }, ensure_ascii=False)
            cache.put(key, text, {"model": out.get("llm_model")})
            budget.release(count_as_paid=True)
            accounted = True
            ledger.record(
                provider="yandex_studio",
                task="interpretation",
                status="ok",
                cost_rub=None,
                note=f"cache_key={key[:12]}",
            )
        else:
            budget.release(count_as_paid=True)
            accounted = True
            ledger.record(
                provider="yandex_studio",
                task="interpretation",
                status=out.get("llm_status") or "error",
                note=out.get("llm_error"),
            )
        out["llm_cache_hit"] = False
        return out
    finally:
        if not accounted:
            # A cancelled/timed-out provider call may already have been billed.
            budget.release(count_as_paid=True)
        cache.release(key)


def persist_summary_to_knowledge(summary: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    """Optional Stage E hook: copy Task1 summary evidence into shared knowledge PG.

    Safe no-op when KNOWLEDGE_DATABASE_URL is unset. Does not change summary.
    """
    import os

    if not os.environ.get("KNOWLEDGE_DATABASE_URL"):
        return {"persisted": False, "reason": "KNOWLEDGE_DATABASE_URL not set"}
    try:
        from osint_agent.knowledge.bridge import KnowledgeBridge
        from osint_agent.knowledge.pg_repository import repository_from_env

        repo = repository_from_env()
        try:
            out = KnowledgeBridge(repo).persist_market_evidence(
                summary,
                workspace_id=workspace_id,
                inn=summary.get("legal_entity_inn"),
            )
            out["persisted"] = True
            return out
        finally:
            repo.close()
    except Exception as exc:  # noqa: BLE001
        return {"persisted": False, "reason": str(exc)[:200]}


async def discover_reports_for_company(
    summary: dict[str, Any],
    *,
    workspace_id: str | None = None,
    fetch_externals: bool = True,
) -> dict[str, Any]:
    """§3 / §7: auto-find industry reports from the product profile — no user file drop.

    Safe no-op without KNOWLEDGE_DATABASE_URL or network. Never claims
    Business Incognita as a source (that connector is requires_source_agreement).
    """
    import asyncio
    import os

    try:
        from osint_agent.knowledge.discovery.pipeline import discover_and_ingest
        from osint_agent.knowledge.discovery.queries import ProductProfile
        from osint_agent.knowledge.env import apply_knowledge_env, knowledge_dsn
        from osint_agent.knowledge.pg_repository import KnowledgePgRepository

        apply_knowledge_env()  # .env → os.environ first
        dsn = knowledge_dsn()
        if not dsn:
            return {"discovered": False, "reason": "KNOWLEDGE_DATABASE_URL is not set"}
        profile = ProductProfile.from_analysis(summary)
        repo = KnowledgePgRepository(dsn)
        try:
            result = await discover_and_ingest(
                profile,
                repo,
                workspace_id=workspace_id or summary.get("workspace_id") or "default",
                fetch_externals=fetch_externals,
            )
        finally:
            close = getattr(repo, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass
        return {
            "discovered": True,
            "product": profile.product,
            "queries": result.queries,
            "yandex_hits": len(result.yandex_hits),
            "openalex_works": len(result.openalex_works),
            "ingested": result.ingested,
            "failed": result.failed,
            "by_source": result.by_source,
            "limitations": result.limitations,
            "business_incognita": "requires_source_agreement",
            "note": "citations are not market-growth evidence",
        }
    except Exception as exc:  # noqa: BLE001
        return {"discovered": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
