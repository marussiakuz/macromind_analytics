"""Acceptance checks F01–F15 for analysis fixes (spec Task1 §12)."""

from decimal import Decimal

from osint_agent.market.auto_analysis import (
    build_auto_analysis,
    build_summary_from_accepted,
    validate_llm_claims,
)


def _company():
    return {
        "inn": "7707083893",
        "name": "ПАО СБЕРБАНК",
        "full_name": "ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО \"СБЕРБАНК РОССИИ\"",
        "okved_main": "64.19",
        "okved_description": "Денежное посредничество",
    }


def test_f01_company_not_own_competitor():
    regs = {
        "contracts": {
            "items": [{
                "id": "c1",
                "fields": {"Заказчик": "ООО Ромашка, ул. Ленина", "Поставщики": "ПАО СБЕРБАНК"},
                "amount": 10,
            }]
        },
        "legalCases": {
            "items": [{
                "id": "1",
                "fields": {
                    "Истцы": "ПАО СБЕРБАНК",
                    "Ответчики": "ООО Ромашка, ул. Ленина",
                },
            }]
        },
    }
    out = build_auto_analysis(_company(), None, regs)
    names = [r["name"] for r in out["related_organizations"]]
    assert "ПАО СБЕРБАНК" not in names
    # судебные стороны НЕ попадают в рыночные связи
    assert not any("истец" in (r.get("roles") or []) for r in out["related_organizations"])
    assert any("Ромашка" in n for n in names)


def test_f02_legal_party_not_competitor():
    regs = {
        "legalCases": {"items": [{"id": "1", "fields": {"Истцы": "ООО НеизвестныйПродукт"}}]},
        "contracts": {"items": [{"id": "c1", "fields": {"Заказчик": "Гос", "Поставщики": "ООО Поставщик"}}]},
    }
    out = build_auto_analysis(_company(), None, regs)
    assert out["confirmed_competitors"] == []
    assert out["competitor_status"] == "insufficient_data"
    # судебные события не в рыночном summary
    assert out["legal_events"] == []
    # стороны суда не конкуренты
    names = " ".join(c["name"] for c in out["competitor_candidates"])
    assert "НеизвестныйПродукт" not in names


def test_f03_supplier_customer_roles_not_competition():
    regs = {
        "contracts": {
            "items": [{
                "id": "c1",
                "fields": {"Заказчик": "Гос заказчик", "Поставщики": "ООО Поставщик"},
                "amount": 100,
            }]
        }
    }
    out = build_auto_analysis(_company(), None, regs)
    roles = {}
    for r in out["related_organizations"]:
        roles[r["name"]] = r["roles"]
    assert "заказчик" in roles.get("Гос заказчик", [])
    assert "поставщик" in roles.get("ООО Поставщик", [])
    assert out["confirmed_competitors"] == []
    # кандидаты есть, но не подтверждены
    assert all(c["status"] == "candidate_for_check" for c in out["competitor_candidates"])


def test_f04_legal_comma_name_not_split_into_market():
    """Судебные связи не участвуют в рынке — запятые в ФИО/названиях не важны."""
    regs = {
        "legalCases": {
            "items": [{"id": "1", "fields": {"Истцы": 'ООО "А, Б и В", г. Москва'}}]
        },
        "contracts": {
            "items": [{"id": "c1", "fields": {"Заказчик": 'ООО "А, Б и В", г. Москва'}}]
        },
    }
    out = build_auto_analysis(_company(), None, regs)
    joined = " ".join(r["name"] for r in out["related_organizations"])
    assert 'ООО "А, Б и В"' in joined or "А, Б и В" in joined


def test_f05_okved_is_not_product():
    out = build_auto_analysis(_company(), None, {})
    assert out["product_scope"]["product"] is None
    assert out["product_scope"]["product_status"] == "needs_clarification"
    assert out["product_scope"]["okved"] == "64.19"
    assert out["market_scope"]["product"] is None


def test_f06_aggressive_collection_rejected():
    ev = {"evidence-1"}
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Компания ведет агрессивное взыскание",
            "claim_type": "interpretation",
            "evidence_ids": ["evidence-1"],
            "limitations": [],
        }],
        ev,
    )
    assert accepted == []
    assert rejected and "unsupported_legal_interpretation" in rejected[0]["reject_reasons"]


def test_f07_profit_quality_causal_rejected():
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Высокая рентабельность доказывает качество клиентов",
            "evidence_ids": ["e1"],
        }],
        {"e1"},
    )
    assert accepted == []


def test_f08_latest_year_by_number():
    finances = {"years": [
        {"year": 2019, "revenue": 1, "net_profit": 1},
        {"year": 2021, "revenue": 10, "net_profit": 2},
        {"year": 2020, "revenue": 5, "net_profit": 1},
    ]}
    out = build_auto_analysis(_company(), finances, {})
    assert out["finance_summary"]["latest_year"]["year"] == 2021
    assert out["finance_summary"]["margin"]["margin_pct"] == "20.00"


def test_f09_zero_revenue_no_margin():
    finances = {"years": [{"year": 2021, "revenue": 0, "net_profit": 1}]}
    out = build_auto_analysis(_company(), finances, {})
    assert out["finance_summary"]["margin"]["status"] == "not_calculated"


def test_f10_no_audit_not_invalid():
    out = build_auto_analysis(_company(), {"years": [{"year": 2021, "revenue": 10, "net_profit": 1}]}, {})
    assert out["finance_summary"]["margin"]["status"] == "computed"
    # отсутствие аудита не делает данные «недостоверными»
    assert not any("недостовер" in str(x).lower() for x in out.get("limitations", []))


def test_f11_procurement_not_tam():
    regs = {"contracts": {"items": [{"id": "1", "fields": {"Заказчик": "X"}, "amount": 1000}]}}
    out = build_auto_analysis(_company(), None, regs)
    assert out["estimates_rf"] is None
    assert out["observed_procurement"]["observed_procurement_value"] == "1000"
    assert out["observed_procurement"]["is_tam"] is False


def test_f12_false_number_claim_rejected_by_missing_evidence():
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Объем рынка 100 млрд",
            "evidence_ids": ["fake-999"],
            "claim_type": "fact",
        }],
        {"evidence-1"},
    )
    assert accepted == []
    assert any("unknown_evidence" in r for r in rejected[0]["reject_reasons"])


def test_f13_no_blank_evidence_fill():
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Рынок растет",
            "evidence_ids": [],
            "claim_type": "interpretation",
        }],
        {"e1", "e2"},
    )
    assert accepted == []
    assert "missing_evidence" in rejected[0]["reject_reasons"]
    # не подставили e1/e2
    assert rejected[0]["evidence_ids"] == []


def test_f14_summary_from_accepted_only():
    text, risks = build_summary_from_accepted([])
    assert "требуются доказательства" in text.lower() or "нет принятых" in text.lower()
    text2, _ = build_summary_from_accepted([{
        "statement": "Факт подтвержден",
        "section": "russian_market",
    }])
    assert "Факт подтвержден" in text2


def test_f15_risk_without_basis_not_published():
    # risk only if accepted claim contains risk marker
    _, risks = build_summary_from_accepted([{"statement": "Все хорошо", "section": "x"}])
    assert risks == []


def test_model_cannot_self_verify_claim():
    accepted, rejected = validate_llm_claims([
        {"statement": "Компания участвует в деле", "evidence_ids": ["e1"],
         "verification_status": "verified"}
    ], {"e1"})
    assert rejected == []
    assert accepted[0]["verification_status"] == "needs_review"


def test_legal_claim_cannot_bypass_guard_with_subject_word():
    accepted, rejected = validate_llm_claims([
        {"statement": "Предмет дела подтверждает агрессивную политику", "evidence_ids": ["e1"]}
    ], {"e1"})
    assert not accepted
    assert rejected[0]["reject_reasons"] == ["unsupported_legal_interpretation"]


def test_string_ids_are_not_iterated_as_individual_citations():
    accepted, rejected = validate_llm_claims([
        {"statement": "fact", "evidence_ids": "e1"}
    ], {"e", "1"})
    assert not accepted
    assert rejected[0]["reason"] == "invalid_claim_fields"


def test_non_list_claims_and_unknown_types_are_rejected():
    assert validate_llm_claims({"statement": "fact"}, {"e1"})[0] == []
    assert validate_llm_claims([
        {"statement": "fact", "evidence_ids": ["e1"], "claim_type": "verified_fact"}
    ], {"e1"})[0] == []
