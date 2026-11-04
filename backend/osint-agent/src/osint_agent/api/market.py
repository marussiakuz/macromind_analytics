"""Market research API routes (plan §15, prefix /api/v1/market)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from osint_agent.market.models import (
    Estimate,
    EstimateKind,
    EstimateMethod,
    MarketScope,
    Observation,
    StudyPassport,
)
from osint_agent.market.competitors import (
    Competitor,
    CompetitorKind,
    FeatureAssessment,
    VRIOAnswer,
    VRIOAssessment,
    VRIOCell,
    competitor_table,
    findings_summary,
    interpret_vrio,
    select_competitors,
)
from osint_agent.market.positioning import FeatureSpec, MDSInputError, run_mds
from osint_agent.market.delphi import (
    DelphiRound,
    ExpertResponse,
    add_response,
    close_round,
    revise_response,
    summarize,
)
from osint_agent.market.repository import MarketRepository, VersionConflict
from osint_agent.market.sizing import SizingError, bottom_up_demand, bottom_up_potential, top_down
from osint_agent.market.triangulation import compare_estimates
from osint_agent.market.report import render_market_report_html
from osint_agent.market.auto_analysis import (
    add_llm_interpretation,
    add_llm_interpretation_cached,
    attach_external_evidence,
    build_auto_analysis,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])

_repo: MarketRepository | None = None


def get_repo() -> MarketRepository:
    global _repo
    if _repo is None:
        # Постоянное хранилище (spec Task1 §2: не :memory:)
        import os

        db_path = os.environ.get("MARKET_DB_PATH") or "data/market.db"
        try:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        except OSError:
            pass
        _repo = MarketRepository(db_path)
    return _repo


def set_repo(repo: MarketRepository | None) -> None:
    global _repo
    _repo = repo


class ScopeIn(BaseModel):
    product: str
    customer_job: str | None = None
    buyer: str | None = None
    payer: str | None = None
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    reference_period: str | None = None
    measure_type: str = "revenue"
    buyer_unit: str | None = None


class CreateStudyIn(BaseModel):
    title: str
    scope: ScopeIn
    owner: str = "local"
    as_of: str | None = None
    notes: str | None = None


class ObservationIn(BaseModel):
    metric: str
    value: str | None = None
    unit: str
    geography: str | None = None
    reference_period: str | None = None
    source_id: str
    source_locator: str | None = None
    status: str = "unreviewed"


class TopDownIn(BaseModel):
    base: str
    shares: list[str]
    currency: str = "RUB"
    geography: str = "RF"
    measure_type: str = "revenue"
    period: str | None = None


class SegmentIn(BaseModel):
    name: str
    n_eligible: int
    acv_potential: str
    p_buy: str | None = None
    acv_buyers: str | None = None
    spend_includes_nonbuyers: bool = False


class BottomUpIn(BaseModel):
    segments: list[SegmentIn]
    currency: str = "RUB"
    geography: str = "RF"
    measure_type: str = "revenue"
    period: str | None = None


class CompareIn(BaseModel):
    a_value: str | None = None
    b_value: str | None = None
    a_kind: str = "potential"
    b_kind: str = "potential"
    measure_type: str = "revenue"
    geography: str = "RF"
    currency: str = "RUB"
    period: str | None = None
    shared_evidence: bool = False


def _estimate_json(e: Estimate) -> dict[str, Any]:
    return {
        "method": e.method.value,
        "kind": e.kind.value,
        "measure_type": e.measure_type,
        "geography": e.geography,
        "currency": e.currency,
        "period": e.period,
        "formula": e.formula,
        "value": None if e.value is None else format(e.value, "f"),
        "unit": e.unit,
        "status": e.status,
        "log": e.log,
        "limitations": e.limitations,
    }


def _sizing_http(err: SizingError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error": {
                "code": err.code,
                "message": err.message,
                "fields": err.fields,
                "retryable": False,
            }
        },
    )


@router.post("/studies", status_code=201)
async def create_study(body: CreateStudyIn) -> dict[str, Any]:
    scope = MarketScope.model_validate(body.scope.model_dump())
    as_of = None
    if body.as_of:
        from datetime import date

        as_of = date.fromisoformat(body.as_of)
    passport = StudyPassport(title=body.title, scope=scope, owner=body.owner, as_of=as_of, notes=body.notes)
    get_repo().create_study(passport)
    return _study_json(passport)


@router.get("/studies")
async def list_studies(
    owner: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    items = get_repo().list_studies(owner=owner, limit=limit, offset=offset)
    return {"items": [_study_json(s) for s in items], "count": len(items)}


@router.get("/studies/{study_id}")
async def get_study(study_id: UUID) -> dict[str, Any]:
    study = get_repo().get_study(study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    observations = get_repo().list_observations(study_id)
    return {
        **_study_json(study),
        "observation_count": len(observations),
        "verified_observations": sum(1 for o in observations if o.status.value == "verified"),
    }


@router.patch("/studies/{study_id}")
async def patch_scope(study_id: UUID, body: ScopeIn, expected_version: int = Query(...)) -> dict[str, Any]:
    scope = MarketScope.model_validate(body.model_dump())
    try:
        study = get_repo().update_scope(study_id, scope, expected_version)
    except VersionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "VERSION_CONFLICT",
                    "message": f"Ожидаемая версия не совпадает (текущая {exc.current})",
                    "fields": ["version"],
                    "retryable": False,
                }
            },
        ) from exc
    if study is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    return _study_json(study)


@router.post("/studies/{study_id}/evidence", status_code=201)
async def add_evidence(study_id: UUID, body: ObservationIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    obs = Observation.model_validate(body.model_dump())
    get_repo().add_observation(study_id, obs)
    return {"id": str(obs.id), "status": obs.status.value, "metric": obs.metric}


@router.get("/studies/{study_id}/evidence")
async def list_evidence(study_id: UUID) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    items = get_repo().list_observations(study_id)
    return {
        "items": [
            {
                "id": str(o.id),
                "metric": o.metric,
                "value": None if o.value is None else format(o.value, "f"),
                "unit": o.unit,
                "geography": o.geography,
                "reference_period": o.reference_period,
                "source_id": o.source_id,
                "status": o.status.value,
            }
            for o in items
        ]
    }


@router.post("/studies/{study_id}/calculate/top-down")
async def calc_top_down(study_id: UUID, body: TopDownIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    try:
        est = top_down(
            body.base,
            body.shares,
            currency=body.currency,
            geography=body.geography,
            measure_type=body.measure_type,
            period=body.period,
        )
    except SizingError as exc:
        raise _sizing_http(exc) from exc
    return _estimate_json(est)


@router.post("/studies/{study_id}/calculate/bottom-up")
async def calc_bottom_up(study_id: UUID, body: BottomUpIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    segments = [s.model_dump() for s in body.segments]
    try:
        pot = bottom_up_potential(
            segments,
            currency=body.currency,
            geography=body.geography,
            measure_type=body.measure_type,
            period=body.period,
        )
        dem = bottom_up_demand(
            segments,
            currency=body.currency,
            geography=body.geography,
            measure_type=body.measure_type,
            period=body.period,
        )
    except SizingError as exc:
        raise _sizing_http(exc) from exc
    return {"potential": _estimate_json(pot), "demand": _estimate_json(dem)}


@router.post("/studies/{study_id}/triangulate")
async def triangulate(study_id: UUID, body: CompareIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")

    def mk(value: str | None, kind: str) -> Estimate | None:
        return Estimate(
            method=EstimateMethod.top_down,
            kind=EstimateKind(kind),
            measure_type=body.measure_type,
            geography=body.geography,
            currency=body.currency,
            period=body.period,
            formula="manual",
            value=None if value is None else __import__("decimal").Decimal(value),
        )

    result = compare_estimates(
        mk(body.a_value, body.a_kind),
        mk(body.b_value, body.b_kind),
        shared_evidence=body.shared_evidence,
    )
    return {
        "status": result.status,
        "divergence": None if result.divergence is None else format(result.divergence, "f"),
        "message": result.message,
        "reasons": result.reasons,
    }


@router.post("/bindings", status_code=201)
async def create_binding(
    study_id: UUID,
    product_scope_id: str | None = None,
    project_id: str | None = None,
    legal_entity_inn: str | None = None,
    report_version: int | None = None,
) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    binding_id = get_repo().create_binding(
        study_id,
        product_scope_id=product_scope_id,
        project_id=project_id,
        legal_entity_inn=legal_entity_inn,
        report_version=report_version,
    )
    return {"id": binding_id, "study_id": str(study_id)}


@router.get("/summaries")
async def summaries(
    legal_entity_inn: str | None = None,
    project_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Сводки без запуска внешнего поиска (plan §15)."""
    rows = get_repo().list_bindings(legal_entity_inn=legal_entity_inn, project_id=project_id)[:limit]
    items = []
    for row in rows:
        study = get_repo().get_study(row["study_id"])
        if study is None:
            continue
        items.append(
            {
                "binding_id": row["id"],
                "study_id": row["study_id"],
                "report_version": row["report_version"],
                "binding_revision": row["binding_revision"],
                "legal_entity_inn": row["legal_entity_inn"],
                "project_id": row["project_id"],
                "product_scope_id": row["product_scope_id"],
                "title": study.title,
                "market_scope": study.scope.model_dump(),
                "review_status": "draft",
            }
        )
    return {"items": items, "count": len(items)}


class CompetitorIn(BaseModel):
    company_name: str
    product_name: str
    kind: str = "direct"
    identifiers: dict[str, str] = Field(default_factory=dict)
    market: str | None = None
    inclusion_reason: str | None = None
    confirmed: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None


class FeatureIn(BaseModel):
    competitor_id: str
    feature: str
    value_numeric: str | None = None
    unit: str | None = None
    value_scale: str | None = None
    evidence: str | None = None


class VRIOIn(BaseModel):
    competitor_id: str
    resource: str
    v: str = "unknown"
    r: str = "unknown"
    i: str = "unknown"
    o: str = "unknown"
    evidence_v: str | None = None
    evidence_r: str | None = None
    evidence_i: str | None = None
    evidence_o: str | None = None


# in-memory store for competitors per study (v1; durable store later)
_COMPETITORS: dict[str, list[Competitor]] = {}
_FEATURES: dict[str, list[FeatureAssessment]] = {}
_VRIO: dict[str, list[VRIOAssessment]] = {}


@router.get("/studies/{study_id}/competitors")
async def list_competitors(study_id: UUID) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    comps = _COMPETITORS.get(str(study_id), [])
    feats = _FEATURES.get(str(study_id), [])
    vrios = _VRIO.get(str(study_id), [])
    included, excluded = select_competitors([c.model_dump() for c in comps])
    findings = findings_summary(included, excluded)
    return {
        "included": [
            {
                "id": str(c.id),
                "company_name": c.company_name,
                "product_name": c.product_name,
                "kind": c.kind.value,
                "inclusion_reason": c.inclusion_reason,
                "confirmed": c.confirmed,
            }
            for c in findings.included
        ],
        "excluded": [
            {
                "id": str(c.id),
                "company_name": c.company_name,
                "product_name": c.product_name,
                "exclusion_reason": c.exclusion_reason,
            }
            for c in findings.excluded
        ],
        "incompleteness_note": findings.incompleteness_note,
        "features": competitor_table(included, feats),
        "vrio": [
            {
                "competitor_id": str(v.competitor_id),
                "resource": v.resource,
                "interpretation": interpret_vrio(v),
                "v": v.v.answer.value,
                "r": v.r.answer.value,
                "i": v.i.answer.value,
                "o": v.o.answer.value,
            }
            for v in vrios
        ],
    }


@router.post("/studies/{study_id}/competitors", status_code=201)
async def add_competitor(study_id: UUID, body: CompetitorIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    try:
        comp = Competitor.model_validate({**body.model_dump(), "kind": CompetitorKind(body.kind)})
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _COMPETITORS.setdefault(str(study_id), []).append(comp)
    return {"id": str(comp.id), "company_name": comp.company_name, "product_name": comp.product_name}


@router.post("/studies/{study_id}/competitors/features", status_code=201)
async def add_feature(study_id: UUID, body: FeatureIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    feat = FeatureAssessment.model_validate(body.model_dump())
    _FEATURES.setdefault(str(study_id), []).append(feat)
    return {"id": f"{feat.competitor_id}:{feat.feature}"}


@router.post("/studies/{study_id}/competitors/vrio", status_code=201)
async def add_vrio(study_id: UUID, body: VRIOIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")

    def cell(ans: str, ev: str | None) -> VRIOCell:
        return VRIOCell(answer=VRIOAnswer(ans), evidence=ev)

    try:
        a = VRIOAssessment(
            competitor_id=UUID(body.competitor_id),
            resource=body.resource,
            v=cell(body.v, body.evidence_v),
            r=cell(body.r, body.evidence_r),
            i=cell(body.i, body.evidence_i),
            o=cell(body.o, body.evidence_o),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _VRIO.setdefault(str(study_id), []).append(a)
    return {"interpretation": interpret_vrio(a)}


class MDSFeatureIn(BaseModel):
    name: str
    scale: float
    weight: float = 1.0
    reference: float = 0.0


class MDSObjectIn(BaseModel):
    id: str
    values: dict[str, float | None]


class MDSIn(BaseModel):
    objects: list[MDSObjectIn]
    features: list[MDSFeatureIn]


class DelphiCreateIn(BaseModel):
    question: str
    unit: str = "RUB"


class DelphiResponseIn(BaseModel):
    participant: str
    competency: str | None = None
    value: str | None = None
    low: str | None = None
    high: str | None = None
    explanation: str | None = None
    sources: list[str] = Field(default_factory=list)
    revision_reason: str | None = None
    supersedes: str | None = None


_ROUNDS: dict[str, list[DelphiRound]] = {}


@router.post("/studies/{study_id}/mds")
async def calc_mds(study_id: UUID, body: MDSIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    features = [
        FeatureSpec(name=f.name, scale=f.scale, weight=f.weight, reference=f.reference)
        for f in body.features
    ]
    values = [[o.values.get(f.name) for f in body.features] for o in body.objects]
    ids = [o.id for o in body.objects]
    try:
        result = run_mds(ids, values, features)
    except MDSInputError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": exc.code, "message": exc.message, "fields": exc.fields, "retryable": False}},
        ) from exc
    return {
        "status": result.status,
        "message": result.message,
        "object_ids": result.object_ids,
        "coordinates": [{"id": i, "x": x, "y": y} for i, (x, y) in zip(result.object_ids, result.coordinates)],
        "distance_matrix": result.distance_matrix,
        "map_distances": result.map_distances,
        "relative_distance_error": result.relative_distance_error,
        "features_used": result.features_used,
        "excluded": result.excluded,
        "method": result.method,
        "axes": ["Измерение 1", "Измерение 2"],
    }


@router.post("/studies/{study_id}/expert-rounds", status_code=201)
async def create_round(study_id: UUID, body: DelphiCreateIn) -> dict[str, Any]:
    if get_repo().get_study(study_id) is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    rnd = DelphiRound(id=uuid4(), study_id=str(study_id), question=body.question, unit=body.unit)
    _ROUNDS.setdefault(str(study_id), []).append(rnd)
    return {"id": str(rnd.id), "status": rnd.status.value, "question": rnd.question}


@router.get("/studies/{study_id}/expert-rounds")
async def list_rounds(study_id: UUID) -> dict[str, Any]:
    rounds = _ROUNDS.get(str(study_id), [])
    return {"items": [summarize(r) for r in rounds]}


@router.post("/studies/{study_id}/expert-rounds/{round_id}/responses", status_code=201)
async def add_round_response(study_id: UUID, round_id: UUID, body: DelphiResponseIn) -> dict[str, Any]:
    rnd = _find_round(str(study_id), round_id)
    if rnd.status.value == "closed":
        raise HTTPException(status_code=409, detail="Раунд закрыт")
    if body.supersedes:
        try:
            resp = revise_response(
                rnd,
                UUID(body.supersedes),
                ExpertResponse(
                    participant=body.participant,
                    competency=body.competency,
                    value=body.value,
                    low=body.low,
                    high=body.high,
                    explanation=body.explanation,
                    sources=body.sources,
                    revision_reason=body.revision_reason,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="revision_reason обязателен при правке") from exc
    else:
        resp = add_response(
            rnd,
            ExpertResponse(
                participant=body.participant,
                competency=body.competency,
                value=body.value,
                low=body.low,
                high=body.high,
                explanation=body.explanation,
                sources=body.sources,
            ),
        )
    return {"id": str(resp.id), "round_no": resp.round_no}


@router.post("/studies/{study_id}/expert-rounds/{round_id}/close")
async def close_round_route(study_id: UUID, round_id: UUID) -> dict[str, Any]:
    rnd = _find_round(str(study_id), round_id)
    return close_round(rnd)


def _find_round(study_id: str, round_id: UUID) -> DelphiRound:
    for r in _ROUNDS.get(study_id, []):
        if r.id == round_id:
            return r
    raise HTTPException(status_code=404, detail="Раунд не найден")


class AutoAnalysisIn(BaseModel):
    company: dict[str, Any] | None = None
    finances: dict[str, Any] | None = None
    registries: dict[str, Any] = Field(default_factory=dict)
    site_text: str | None = None
    extra_sources: list[str] | None = None
    workspace_id: str | None = None
    request_key: str | None = None
    use_llm: bool = True
    use_external_evidence: bool = True
    use_discovery: bool = True


@router.post("/auto-analysis")
async def auto_analysis(body: AutoAnalysisIn) -> dict[str, Any]:
    """Воронка → Проверить юр. лицо → после финотчёта.

    Склейка существующих шагов: build → Yandex/OpenAlex → discovery → Qwen → version.
    Универсально: без зашитых компаний/отраслей/конкурентов.
    """
    repo = get_repo()
    from osint_agent.market.research_errors import ResearchDependencyError
    inn = (body.company or {}).get("inn")
    job = repo.create_job(kind="auto_analysis", legal_entity_inn=inn, owner_token=body.request_key)
    try:
        from osint_agent.market.universal_analysis import run_company_market_check

        import asyncio
        out = await asyncio.wait_for(run_company_market_check(
            inn=inn or "",
            company=body.company,
            finances=body.finances,
            registries=body.registries,
            site_text=body.site_text,
            extra_sources=body.extra_sources,
            workspace_id=body.workspace_id,
            use_llm=body.use_llm,
            use_external_evidence=body.use_external_evidence,
            use_discovery=body.use_discovery,
            request_key=body.request_key,
            repo=repo,
        ), timeout=1800)  # запас над ResearchBudget.max_seconds: локальная модель на CPU
        saved = out.get("saved") or out
        repo.finish_job(
            job["id"],
            status="completed" if out.get("completeness_status") == "full" else "partial",
            result_version_id=saved.get("analysis_version_id"),
        )
        out["job_id"] = job["id"]
        return out
    except ResearchDependencyError as exc:
        repo.finish_job(job["id"], status="failed", error=f"{exc.source}:{exc.code}")
        raise HTTPException(status_code=503, detail={"error": {
            "code": exc.code, "source": exc.source, "message": exc.public_message,
            "retryable": False, "job_id": job["id"],
        }}) from exc
    except asyncio.TimeoutError as exc:
        repo.finish_job(job["id"], status="failed", error="analysis_timeout")
        raise HTTPException(status_code=504, detail="Источники или модель не ответили вовремя. Прежний отчёт сохранён; повторите исследование.") from exc
    except Exception as exc:
        repo.finish_job(job["id"], status="failed", error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="Анализ не завершен; прежние версии сохранены") from exc


@router.get("/auto-analysis")
async def get_auto_analysis(
    legal_entity_inn: str | None = None,
    study_id: str | None = None,
    version_id: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Восстановление сохранённой версии без повторного вызова модели (F23/F25).

    Старые версии санитизируются: судебные стороны не показываются в рынке;
    analytical_report достраивается, если его ещё не было.
    """
    repo = get_repo()
    if version_id:
        data = repo.get_analysis_version(version_id)
        if not data:
            raise HTTPException(status_code=404, detail="Версия не найдена")
        return _sanitize_analysis_payload(data)
    data = repo.latest_analysis_for(legal_entity_inn=legal_entity_inn, study_id=study_id)
    if not data:
        raise HTTPException(status_code=404, detail="Сохранённый анализ не найден")
    return _sanitize_analysis_payload(data)


def _sanitize_analysis_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Strip court parties from market view; add analytical_report if missing."""
    from osint_agent.market.analytical_report import (
        build_analytical_report,
        render_analytical_report_html,
    )

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else data
    # some versions nest summary under summary_json
    if not summary.get("legal_entity_inn") and isinstance(data.get("summary_json"), dict):
        summary = data["summary_json"]

    rel = list(summary.get("related_organizations") or data.get("related_organizations") or [])
    cleaned = [
        r for r in rel
        if not any(x in (r.get("roles") or []) for x in ("истец", "ответчик"))
    ]
    target = summary if summary else data
    target["related_organizations"] = cleaned
    # legal cases are not market signals
    target["legal_events"] = []
    if "limitations" in target:
        target["limitations"] = [
            x for x in (target.get("limitations") or [])
            if "арбитраж" not in str(x).lower() and "споров" not in str(x).lower()
        ] or target["limitations"]

    if not target.get("analytical_report"):
        report = build_analytical_report(
            target,
            company_name=(target.get("product_scope") or {}).get("company_name")
            or target.get("company_name"),
            inn=target.get("legal_entity_inn"),
        )
        target["analytical_report"] = report
        target["report_html"] = render_analytical_report_html(report)

    # Apply citation integrity to saved reports too; reopening never calls the model.
    report = target.get("analytical_report") or {}
    if report.get("sections") is not None and target.get("external_evidence"):
        from osint_agent.market.analytical_report import finalize_competitors
        report["competitors"] = finalize_competitors(
            report.get("competitors") or {}, target["external_evidence"], target,
        )
        target["report_html"] = render_analytical_report_html(report)

    if summary is not data:
        data["summary"] = summary
    return data


@router.get("/auto-analysis/versions")
async def list_analysis_versions(legal_entity_inn: str | None = None) -> dict[str, Any]:
    return {"items": get_repo().list_analysis_versions(legal_entity_inn)}


@router.get("/studies/{study_id}/report")
async def get_report(study_id: UUID) -> dict[str, Any]:
    """HTML-отчет с рыночным разделом (plan §4.3). Пробелы остаются видимыми."""
    study = get_repo().get_study(study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="Исследование не найдено")
    observations = get_repo().list_observations(study_id)
    comps = _COMPETITORS.get(str(study_id), [])
    included, _ex = select_competitors([c.model_dump() for c in comps])
    html = render_market_report_html(
        study=_study_json(study),
        summary=None,
        top_down=None,
        bottom_up=None,
        triangulation=None,
        competitors=[
            {"company_name": c.company_name, "product_name": c.product_name, "inclusion_reason": c.inclusion_reason}
            for c in included
        ],
        observations=[
            {
                "metric": o.metric,
                "value": None if o.value is None else format(o.value, "f"),
                "unit": o.unit,
                "source_id": o.source_id,
                "status": o.status.value,
            }
            for o in observations
        ],
    )
    return {
        "content_type": "text/html; charset=utf-8",
        "filename": f"market-report-{study_id}.html",
        "html": html,
    }


def _study_json(study: StudyPassport) -> dict[str, Any]:
    return {
        "id": str(study.id),
        "title": study.title,
        "owner": study.owner,
        "version": study.version,
        "as_of": study.as_of.isoformat() if study.as_of else None,
        "money_basis_currency": study.money_basis_currency,
        "notes": study.notes,
        "created_at": study.created_at.isoformat(),
        "market_scope": study.scope.model_dump(),
    }
