"""Fund profile, ACL cache key, industry-independent refusal, chemistry holdout."""

from __future__ import annotations

import os
import uuid

import pytest

from osint_agent.knowledge.cache_keys import cache_key_with_corpus, corpus_snapshot_id
from osint_agent.knowledge.fund_profile import (
    INDUSTRIES,
    FundProfile,
    industry_for,
    standard_doc_metadata,
)
from osint_agent.market.auto_analysis import (
    build_summary_from_accepted,
    refuse_if_insufficient,
    select_evidence_for_claims,
    validate_llm_claims,
)


# --- fund / industry -------------------------------------------------------

def test_industry_presets_include_chemistry():
    chem = industry_for("chemistry")
    assert chem.code == "chemistry"
    assert any("хим" in t for t in chem.ru_terms)
    assert any(u in chem.metric_units for u in ("т", "тонн", "млн т"))
    assert "citations" in chem.non_growth_signals


def test_fund_profile_roundtrip():
    p = FundProfile(
        fund_id="f1", name="Fund", industry="chemistry",
        allowed_workspaces=["ws-a", "ws-b"], require_number_in_evidence=True,
    )
    p2 = FundProfile.from_dict(p.to_dict())
    assert p2.industry == "chemistry"
    assert p2.allowed_workspaces == ["ws-a", "ws-b"]


def test_standard_doc_metadata_fields():
    m = standard_doc_metadata(
        source="openalex", read_level="abstract_only", industry="chemistry",
        doi="10.1/x", original_url="https://doi.org/10.1/x",
    )
    assert m["read_level"] == "abstract_only"
    assert m["industry"] == "chemistry"
    assert m["doi"] == "10.1/x"


# --- ACL in cache ----------------------------------------------------------

def test_cache_key_includes_acl():
    k1 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws",
                               document_ids=["d1"], allowed_workspaces=["ws-a"])
    k2 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws",
                               document_ids=["d1"], allowed_workspaces=["ws-a", "ws-b"])
    k3 = cache_key_with_corpus(model="m", prompt_version="p", system="s",
                               payload={"q": 1}, workspace_id="ws",
                               document_ids=["d1"], allowed_workspaces=None)
    assert k1 != k2
    assert k1 != k3
    assert corpus_snapshot_id(workspace_id="ws", document_ids=["d1"], allowed_workspaces=["a"]) != \
        corpus_snapshot_id(workspace_id="ws", document_ids=["d1"], allowed_workspaces=["b"])


# --- numbers / evidence / refusal (fund-independent) ------------------------

def test_wrong_number_rejected_any_industry():
    ev = {"id": "e1", "statement": "Объем рынка катализаторов 42 млрд рублей", "period": "2024"}
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Объем рынка 999 млрд рублей",
            "claim_type": "fact",
            "evidence_ids": ["e1"],
        }],
        {"e1"},
        evidence_by_id={"e1": ev},
    )
    assert accepted == []
    assert "numbers_not_in_evidence" in rejected[0]["reject_reasons"]


def test_select_evidence_only_from_accepted():
    accepted = [
        {"evidence_ids": ["e1", "missing"]},
        {"evidence_ids": ["e1", "e2"]},
    ]
    by_id = {"e1": {"id": "e1"}, "e2": {"id": "e2"}}
    picked = select_evidence_for_claims(accepted, by_id)
    assert [p["id"] for p in picked] == ["e1", "e2"]


def test_refuse_when_insufficient_data():
    summary = {
        "evidence_refs": [],
        "finance_summary": {},
        "data_completeness": {"has_confirmed_competitors": False},
        "triangulation_status": "insufficient_data",
        "competitor_status": "insufficient_data",
    }
    out = refuse_if_insufficient(summary)
    assert out["analysis_status"] == "insufficient_data"
    assert "insufficient_evidence" in out["refusal_reasons"]
    assert "Недостаточно" in out["llm_summary"]


def test_no_refuse_with_enough_inputs():
    summary = {
        "evidence_refs": [{"id": "e1"}],
        "finance_summary": {"latest_year": {"year": 2024, "revenue": 1}},
        "data_completeness": {},
    }
    out = refuse_if_insufficient(summary)
    assert out.get("analysis_status") == "ok"
    assert "refusal_reasons" not in out


def test_empty_accepted_summary_is_refusal_text():
    text, risks = build_summary_from_accepted([])
    assert "доказательства" in text.lower() or "Нет" in text
    assert risks == []
