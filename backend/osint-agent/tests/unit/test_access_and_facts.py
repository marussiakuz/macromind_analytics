"""Access control + number verification (Astra P1 §6.2)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from osint_agent.knowledge.access import Principal, resolve_principal
from osint_agent.market.auto_analysis import extract_numbers, validate_llm_claims


# --- Principal / workspace -------------------------------------------------

def test_service_token_unrestricted():
    os.environ["KNOWLEDGE_INTERNAL_TOKEN"] = "svc-secret"
    os.environ.pop("KNOWLEDGE_USER_ACCESS", None)
    p = resolve_principal(authorization="Bearer svc-secret")
    assert p.is_service
    assert p.can_use("any-ws")
    assert p.resolve_workspace("other") == "other"


def test_user_cannot_select_foreign_workspace():
    os.environ["KNOWLEDGE_INTERNAL_TOKEN"] = "svc-secret"
    os.environ["KNOWLEDGE_USER_ACCESS"] = "alice:tok-a:ws-1|ws-2;bob:tok-b:ws-3"
    alice = resolve_principal(x_api_key="tok-a")
    assert alice.name == "alice"
    assert alice.can_use("ws-1")
    assert not alice.can_use("ws-3")
    with pytest.raises(Exception):
        alice.resolve_workspace("ws-3")
    assert alice.resolve_workspace("ws-2") == "ws-2"


def test_unknown_token_rejected():
    os.environ["KNOWLEDGE_INTERNAL_TOKEN"] = "svc-secret"
    os.environ["KNOWLEDGE_USER_ACCESS"] = "alice:tok-a:ws-1"
    with pytest.raises(Exception):
        resolve_principal(x_api_key="nope")


def test_default_workspace_is_not_public_for_user():
    os.environ["KNOWLEDGE_INTERNAL_TOKEN"] = "svc"
    os.environ["KNOWLEDGE_USER_ACCESS"] = "alice:tok:ws-1|ws-2"
    p = resolve_principal(x_api_key="tok")
    assert p.resolve_workspace(None) == "ws-1"
    assert p.resolve_workspace("public") == "public"


# --- numbers ---------------------------------------------------------------

def test_extract_numbers_scales():
    nums = extract_numbers("Выручка 12,5 млрд рублей и 18% роста")
    assert any(abs(float(n) - 12_500_000_000) < 1 for n in nums)
    assert any(abs(float(n) - 18) < 0.01 for n in nums)


def test_fake_number_with_real_id_rejected():
    """Astra: существующий ID с чужим числом не проходит."""
    ev = {
        "id": "e1",
        "statement": "Выручка ООО Ромашка за 2019 год составила 125000000 рублей",
        "period": "2019",
    }
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Выручка компании составила 999 млрд рублей",
            "claim_type": "fact",
            "evidence_ids": ["e1"],
            "limitations": [],
        }],
        {"e1"},
        evidence_by_id={"e1": ev},
    )
    assert accepted == []
    assert "numbers_not_in_evidence" in rejected[0]["reject_reasons"]


def test_matching_number_accepted():
    ev = {
        "id": "e1",
        "statement": "Выручка ООО Ромашка за 2019 год составила 125000000 рублей",
        "period": "2019",
    }
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Выручка за 2019 год — 125000000 рублей",
            "claim_type": "fact",
            "evidence_ids": ["e1"],
            "limitations": [],
        }],
        {"e1"},
        evidence_by_id={"e1": ev},
    )
    assert rejected == []
    assert accepted and accepted[0]["verification_status"] == "needs_review"


def test_wrong_period_rejected_structured_fact():
    ev = {"id": "e1", "statement": "Выручка 1000000", "period": "2019"}
    accepted, rejected = validate_llm_claims(
        [{
            "statement": "Показатель за 2021 год",
            "claim_type": "fact",
            "evidence_ids": ["e1"],
            "fact": {"company": "ООО Ромашка", "metric": "revenue", "value": 1000000, "period": "2021"},
        }],
        {"e1"},
        evidence_by_id={"e1": ev},
    )
    assert accepted == []
    assert "fact_period_not_in_evidence" in rejected[0]["reject_reasons"]


def test_statement_without_numbers_still_needs_id():
    accepted, rejected = validate_llm_claims(
        [{"statement": "Рынок растет", "evidence_ids": [], "limitations": []}],
        set(),
    )
    assert accepted == []


# --- API access (ASGI, mocked repo) ---------------------------------------

def test_get_evidence_foreign_id_is_404():
    from osint_agent.api import knowledge as api

    class FakeRepo:
        def get_evidence_by_id(self, evidence_id, allowed_workspaces=None):
            # only returns rows in allowed workspaces
            if allowed_workspaces is not None and "ws-alice" not in allowed_workspaces:
                return None
            if evidence_id == "ev-alice" and (allowed_workspaces is None or "ws-alice" in (allowed_workspaces or [])):
                return {"id": "ev-alice", "workspace_id": "ws-alice", "statement": "ok"}
            return None

    app = FastAPI()
    app.include_router(api.router)
    api.set_repo(FakeRepo())
    try:
        os.environ["KNOWLEDGE_INTERNAL_TOKEN"] = "svc"
        os.environ["KNOWLEDGE_USER_ACCESS"] = "alice:tok-a:ws-alice;bob:tok-b:ws-bob"
        client = TestClient(app)

        r = client.get("/api/v1/knowledge/evidence/ev-alice", headers={"X-Api-Key": "tok-a"})
        assert r.status_code == 200

        # bob cannot read alice's evidence — 404, no existence leak
        r = client.get("/api/v1/knowledge/evidence/ev-alice", headers={"X-Api-Key": "tok-b"})
        assert r.status_code == 404

        # no credentials
        r = client.get("/api/v1/knowledge/evidence/ev-alice")
        assert r.status_code == 401

        # service sees all
        r = client.get("/api/v1/knowledge/evidence/ev-alice", headers={"Authorization": "Bearer svc"})
        assert r.status_code == 200
    finally:
        api.set_repo(None)
