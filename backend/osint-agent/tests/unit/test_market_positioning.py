"""MDS (plan §13, M01–M05) and Delphi rounds (plan §11, D01–D02)."""

from decimal import Decimal
from uuid import uuid4

import pytest

from osint_agent.market.delphi import (
    DelphiRound,
    ExpertResponse,
    RoundStatus,
    add_response,
    close_round,
    revise_response,
    summarize,
)
from osint_agent.market.positioning import FeatureSpec, mds_from_rows, run_mds


def _features():
    return [FeatureSpec("price", 1.0, 0.5), FeatureSpec("time", 1.0, 0.5)]


# M01: square with known distances → 2D recovers pairwise distances
def test_m01_square_recovered():
    # unit square in 2 features
    ids = ["a", "b", "c", "d"]
    values = [
        [0.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [1.0, 1.0],
    ]
    r = run_mds(ids, values, _features())
    assert r.status == "ok"
    assert len(r.coordinates) == 4
    assert r.relative_distance_error is not None
    assert r.relative_distance_error < 1e-6
    # side length ~1
    n = len(r.distance_matrix)
    sides = [r.distance_matrix[i][j] for i in range(n) for j in range(i + 1, n)]
    assert min(sides) > 0.5


# M02: permutation of objects keeps distances
def test_m02_permutation_invariant():
    vals = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    r1 = run_mds(list("abcd"), vals, _features())
    r2 = run_mds(list("dcba"), vals[::-1], _features())
    assert r1.status == r2.status == "ok"
    assert r1.relative_distance_error is not None and r2.relative_distance_error is not None
    assert abs(r1.relative_distance_error - r2.relative_distance_error) < 1e-9


# M03: reflection does not break (we don't assert orientation)
def test_m03_reflection_runs():
    r = run_mds(
        ["a", "b", "c", "d"],
        [[0.0, 0.0], [-1.0, 0.0], [0.0, -1.0], [-1.0, -1.0]],
        _features(),
    )
    assert r.status == "ok"
    assert len(r.coordinates) == 4


# M04: all zero distances → degenerate, no NaN
def test_m04_degenerate_all_zero():
    r = run_mds(
        ["a", "b", "c", "d"],
        [[1.0, 1.0]] * 4,
        _features(),
    )
    assert r.status == "degenerate"
    assert r.message
    for x, y in r.coordinates:
        assert x == 0.0 and y == 0.0
        assert x == x  # not NaN


# M05: incomplete / too few features → understandable reason
def test_m05_insufficient():
    r = run_mds(["a", "b", "c"], [[0, 0], [1, 1], [None, 1]], _features())
    assert r.status == "insufficient_data"
    assert any("пропуск" in e["reason"] for e in r.excluded) or "минимум" in r.message

    r2 = run_mds(["a", "b", "c", "d"], [[0, 0], [1, 1], [2, 2], [3, 3]], [FeatureSpec("x", 1.0)])
    assert r2.status == "insufficient_data"


def test_mds_weights_normalized():
    r = mds_from_rows(
        [
            {"id": "a", "p": 0, "t": 0},
            {"id": "b", "p": 1, "t": 0},
            {"id": "c", "p": 0, "t": 1},
            {"id": "d", "p": 1, "t": 1},
        ],
        ["p", "t"],
        {"p": 1.0, "t": 1.0},
        {"p": 3.0, "t": 1.0},  # сумма ≠ 1 → нормировка
    )
    assert r.status == "ok"
    assert r.relative_distance_error is not None


# D01: one expert is not a panel
def test_d01_single_expert_not_panel():
    rid = uuid4()
    r = DelphiRound(id=rid, study_id="s", question="Объём рынка?", unit="RUB")
    add_response(r, ExpertResponse(participant="E1", value=Decimal("100")))
    s = summarize(r)
    assert s["participant_count"] == 1
    assert "панель не заявлена" in s["note"]


# D02: second-round revision keeps first answer and reason
def test_d02_revision_keeps_original():
    rid = uuid4()
    r = DelphiRound(id=rid, study_id="s", question="Q", unit="RUB")
    first = add_response(r, ExpertResponse(participant="E1", value=Decimal("100"), round_no=1))
    second = ExpertResponse(
        participant="E1",
        value=Decimal("120"),
        round_no=2,
        revision_reason="Уточнил по отчёту Росстата",
    )
    revise_response(r, first.id, second)
    assert len(r.responses) == 2
    assert r.responses[0].value == Decimal("100")
    assert r.responses[1].revision_reason
    assert r.responses[1].supersedes == first.id

    closed = close_round(r)
    assert closed["status"] == "closed"
    assert closed["participant_count"] == 1


def test_delphi_three_values_shown():
    r = DelphiRound(id=uuid4(), study_id="s", question="Q", unit="RUB")
    for name, val in [("A", "10"), ("B", "20"), ("C", "30")]:
        add_response(r, ExpertResponse(participant=name, value=Decimal(val)))
    s = summarize(r)
    assert s["participant_count"] == 3
    assert "все значения" in s["note"]
    assert s["median"] == "20"
    assert s["spread"] == "20"
