"""Market API and storage tests (plan §21 selection)."""

from decimal import Decimal

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from osint_agent.market.models import MarketScope, Observation, StudyPassport
from osint_agent.market.repository import MarketRepository
from osint_agent.api.market import set_repo
from osint_agent.main import app


@pytest.fixture
def repo():
    r = MarketRepository(":memory:")
    set_repo(r)
    yield r
    set_repo(None)
    r.close()


@pytest.fixture
async def client(repo):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


SCOPE = {
    "product": "B2B SaaS для логистики",
    "buyer": "директор по логистике",
    "countries": ["RU"],
    "reference_period": "2024",
    "measure_type": "revenue",
}


async def _create(client, **kw):
    body = {"title": "Рынок логистики", "scope": SCOPE, **kw}
    resp = await client.post("/api/v1/market/studies", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# I03-style: products of one company not mixed
async def test_studies_are_separate_per_product(repo):
    a = StudyPassport(title="A", scope=MarketScope(product="P1"))
    b = StudyPassport(title="B", scope=MarketScope(product="P2"))
    repo.create_study(a)
    repo.create_study(b)
    assert repo.get_study(a.id).scope.product == "P1"
    assert repo.get_study(b.id).scope.product == "P2"


async def test_create_and_get_study(client):
    data = await _create(client)
    got = await client.get(f"/api/v1/market/studies/{data['id']}")
    assert got.status_code == 200
    assert got.json()["market_scope"]["product"] == SCOPE["product"]
    assert got.json()["observation_count"] == 0


async def test_missing_study_404(client):
    resp = await client.get("/api/v1/market/studies/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404


async def test_version_conflict_409(client):
    data = await _create(client)
    resp = await client.patch(
        f"/api/v1/market/studies/{data['id']}",
        params={"expected_version": 99},
        json=SCOPE,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "VERSION_CONFLICT"


async def test_evidence_roundtrip(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/evidence",
        json={
            "metric": "market_size_rf",
            "value": "1000000000",
            "unit": "RUB/year",
            "geography": "RF",
            "reference_period": "2024",
            "source_id": "src-1",
            "source_locator": "table 1 row 2",
            "status": "verified",
        },
    )
    assert resp.status_code == 201
    listed = await client.get(f"/api/v1/market/studies/{data['id']}/evidence")
    items = listed.json()["items"]
    assert items[0]["value"] == "1000000000"
    assert items[0]["status"] == "verified"


# C01 via API
async def test_top_down_via_api(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/calculate/top-down",
        json={"base": "10000000000", "shares": ["0.20", "0.50"]},
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["value"]) == Decimal("1000000000")


# C02–C03 via API
async def test_bottom_up_potential_and_demand(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/calculate/bottom-up",
        json={
            "segments": [
                {
                    "name": "h",
                    "n_eligible": 1000,
                    "acv_potential": "100000",
                    "p_buy": "0.25",
                    "acv_buyers": "100000",
                }
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["potential"]["value"]) == Decimal("100000000")
    assert Decimal(body["demand"]["value"]) == Decimal("25000000")


# C05 via API — 422 with stable error code
async def test_double_count_422(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/calculate/bottom-up",
        json={
            "segments": [
                {
                    "name": "h",
                    "n_eligible": 10,
                    "acv_potential": "1",
                    "p_buy": "0.5",
                    "acv_buyers": "1",
                    "spend_includes_nonbuyers": True,
                }
            ]
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "DOUBLE_COUNT"


async def test_triangulate_not_comparable_kinds(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/triangulate",
        json={"a_value": "100", "b_value": "100", "a_kind": "potential", "b_kind": "demand"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_comparable"
    assert "kind" in resp.json()["reasons"]


async def test_triangulate_close(client):
    data = await _create(client)
    resp = await client.post(
        f"/api/v1/market/studies/{data['id']}/triangulate",
        json={"a_value": "100", "b_value": "120"},
    )
    assert resp.json()["status"] == "close"


async def test_summaries_no_search_and_multiple_bindings(client, repo):
    data = await _create(client)
    sid = data["id"]
    await client.post(
        "/api/v1/market/bindings",
        params={"study_id": sid, "legal_entity_inn": "7707083893", "project_id": "p1"},
    )
    await client.post(
        "/api/v1/market/bindings",
        params={"study_id": sid, "legal_entity_inn": "7707083893", "project_id": "p2"},
    )
    resp = await client.get("/api/v1/market/summaries", params={"legal_entity_inn": "7707083893"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 2  # не выбирать произвольно одну


async def test_competitors_and_vrio(client):
    data = await _create(client)
    sid = data["id"]
    created = []
    for i in range(3):
        r = await client.post(
            f"/api/v1/market/studies/{sid}/competitors",
            json={"company_name": f"C{i}", "product_name": f"P{i}"},
        )
        assert r.status_code == 201
        created.append(r.json()["id"])
    listed = await client.get(f"/api/v1/market/studies/{sid}/competitors")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["included"]) == 3
    assert body["incompleteness_note"] is not None

    v = await client.post(
        f"/api/v1/market/studies/{sid}/competitors/vrio",
        json={"competitor_id": created[0], "resource": "data", "v": "yes", "r": "yes", "i": "yes", "o": "unknown"},
    )
    assert v.status_code == 201
    assert "не подтверждено" in v.json()["interpretation"].lower() or "недостаточно" in v.json()["interpretation"].lower()


async def test_mds_route(client):
    data = await _create(client)
    sid = data["id"]
    body = {
        "objects": [
            {"id": "a", "values": {"p": 0, "t": 0}},
            {"id": "b", "values": {"p": 1, "t": 0}},
            {"id": "c", "values": {"p": 0, "t": 1}},
            {"id": "d", "values": {"p": 1, "t": 1}},
        ],
        "features": [
            {"name": "p", "scale": 1.0, "weight": 0.5},
            {"name": "t", "scale": 1.0, "weight": 0.5},
        ],
    }
    resp = await client.post(f"/api/v1/market/studies/{sid}/mds", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["status"] == "ok"
    assert len(out["coordinates"]) == 4
    assert out["axes"] == ["Измерение 1", "Измерение 2"]
    assert out["relative_distance_error"] is not None


async def test_delphi_round_flow(client):
    data = await _create(client)
    sid = data["id"]
    r = await client.post(
        f"/api/v1/market/studies/{sid}/expert-rounds",
        json={"question": "Объём рынка РФ?", "unit": "RUB"},
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    await client.post(
        f"/api/v1/market/studies/{sid}/expert-rounds/{rid}/responses",
        json={"participant": "E1", "value": "100"},
    )
    await client.post(
        f"/api/v1/market/studies/{sid}/expert-rounds/{rid}/responses",
        json={"participant": "E2", "value": "140"},
    )
    closed = await client.post(f"/api/v1/market/studies/{sid}/expert-rounds/{rid}/close")
    assert closed.status_code == 200
    body = closed.json()
    assert body["status"] == "closed"
    assert body["participant_count"] == 2
    assert body["median"] is not None


async def test_research_auth_error_is_actionable_and_keeps_previous_report(client,repo,monkeypatch):
    from osint_agent.market.research_errors import ResearchDependencyError
    old=repo.save_analysis_version({'legal_entity_inn':'123','company_name':'Тест'})
    async def fail(**kwargs):
        raise ResearchDependencyError('yandex_search','auth_error')
    monkeypatch.setattr('osint_agent.market.universal_analysis.run_company_market_check',fail)
    response=await client.post('/api/v1/market/auto-analysis',json={'company':{'inn':'123'}})
    assert response.status_code==503
    error=response.json()['detail']['error']
    assert error['code']=='auth_error' and error['source']=='yandex_search'
    assert error['retryable'] is False
    assert 'авторизацию' in error['message']
    assert repo.latest_analysis_for(legal_entity_inn='123')['analysis_version_id']==old['analysis_version_id']
    row=repo.connect().execute('select status,error from research_jobs where id=?',(error['job_id'],)).fetchone()
    assert row['status']=='failed' and row['error']=='yandex_search:auth_error'
