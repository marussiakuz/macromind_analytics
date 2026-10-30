"""Reference checks C01–C16 from MIMO_MARKET_MODULE_PLAN.md §20."""

from decimal import Decimal

import pytest

from osint_agent.market.models import Estimate, EstimateKind, EstimateMethod
from osint_agent.market.sizing import (
    SizingError,
    bottom_up_demand,
    bottom_up_potential,
    sensitivity_base,
    top_down,
    validate_segment,
)
from osint_agent.market.triangulation import compare_estimates


def est(value, kind=EstimateKind.potential, period="2024", currency="RUB", measure="revenue", geo="RF"):
    return Estimate(
        method=EstimateMethod.top_down,
        kind=kind,
        measure_type=measure,
        geography=geo,
        currency=currency,
        period=period,
        formula="test",
        value=Decimal(str(value)) if value is not None else None,
    )


# --- C01 ---
def test_c01_top_down_shares():
    result = top_down("10000000000", ["0.20", "0.50"])
    assert result.value == Decimal("1000000000")
    assert result.method == EstimateMethod.top_down
    assert result.kind == EstimateKind.potential


# --- C02 ---
def test_c02_bottom_up_potential():
    result = bottom_up_potential(
        [{"name": "h", "n_eligible": 1000, "acv_potential": "100000"}]
    )
    assert result.value == Decimal("100000000")
    assert result.kind == EstimateKind.potential


# --- C03 ---
def test_c03_demand_keeps_potential_distinct():
    segs = [{"name": "h", "n_eligible": 1000, "acv_potential": "100000", "p_buy": "0.25", "acv_buyers": "100000"}]
    pot = bottom_up_potential(segs)
    dem = bottom_up_demand(segs)
    assert pot.value == Decimal("100000000")
    assert dem.value == Decimal("25000000")
    assert pot.kind != dem.kind


# --- C04 ---
def test_c04_segments_sum_without_unweighted_average():
    result = bottom_up_potential(
        [
            {"name": "A", "n_eligible": 100, "acv_potential": "100000"},
            {"name": "B", "n_eligible": 10, "acv_potential": "500000"},
        ]
    )
    assert result.value == Decimal("15000000")


# --- C05 ---
def test_c05_double_count_rejected():
    seg = {
        "name": "h",
        "n_eligible": 10,
        "acv_potential": "1",
        "p_buy": "0.5",
        "acv_buyers": "1",
        "spend_includes_nonbuyers": True,
    }
    with pytest.raises(SizingError) as exc:
        validate_segment(seg)
    assert exc.value.code == "DOUBLE_COUNT"


# --- C06 / C07 / C08 / C09 / C10 / C11 / C12 ---
def test_c06_close_divergence():
    r = compare_estimates(est(100), est(120))
    assert r.status == "close"
    assert r.divergence is not None
    assert abs(r.divergence - Decimal("2") / Decimal("11")) < Decimal("0.000001")


def test_c07_divergent():
    r = compare_estimates(est(100), est(140))
    assert r.status == "divergent"
    assert r.divergence is not None and r.divergence > Decimal("0.30")


def test_c08_both_zero():
    r = compare_estimates(est(0), est(0))
    assert r.status == "both_zero"
    assert r.divergence is None


def test_c09_one_zero_positive():
    r = compare_estimates(est(0), est(100))
    assert r.status == "divergent"
    assert r.divergence == Decimal("2.000000") or r.divergence == Decimal(2)


def test_c10_unknown_not_zero():
    r = compare_estimates(est(None), est(100))
    assert r.status == "insufficient_data"
    assert r.divergence is None


def test_c11_potential_vs_demand_not_comparable():
    r = compare_estimates(est(100, kind=EstimateKind.potential), est(100, kind=EstimateKind.demand))
    assert r.status == "not_comparable"
    assert "kind" in r.reasons


def test_c12_different_periods_not_comparable():
    r = compare_estimates(est(100, period="2020"), est(100, period="2024", currency="USD"))
    assert r.status == "not_comparable"
    assert "reference_period" in r.reasons
    assert "currency" in r.reasons


# --- C13 ---
def test_c13_invalid_p_and_acv():
    with pytest.raises(Exception):
        validate_segment({"name": "x", "n_eligible": 1, "acv_potential": "1", "p_buy": "1.1"})
    with pytest.raises(Exception):
        validate_segment({"name": "x", "n_eligible": 1, "acv_potential": "-5"})


def test_c13_nan_rejected():
    with pytest.raises(SizingError):
        top_down("NaN", ["1"])
    with pytest.raises(SizingError):
        top_down("Infinity", ["1"])


# --- C14 ---
def test_c14_sensitivity_is_scenario_not_ci():
    s = sensitivity_base(Decimal("100000"), 1000, Decimal("80000"), Decimal("120000"))
    assert s.low == Decimal("80000000")
    assert s.base == Decimal("100000000")
    assert s.high == Decimal("120000000")


# --- C15 shared evidence (via compare flag) ---
def test_c15_shared_evidence_flag():
    r = compare_estimates(est(100), est(110), shared_evidence=True)
    assert r.status == "shared_evidence"


# --- C16 partial geography documented ---
def test_c16_estimate_can_note_partial_geography():
    e = bottom_up_potential(
        [{"name": "RU", "n_eligible": 10, "acv_potential": "1"}],
        geography="3 countries only",
    )
    assert e.geography == "3 countries only"
    assert e.status == "computed"


# Границы D
def test_d_boundaries_exact():
    # D = 0.20 → close: |A-B|/((A+B)/2)=0.2 → B = A*1.2/0.8? wait
    # (B-A)/((A+B)/2)=0.2 → 2(B-A)=0.2(A+B) → 2B-2A=0.2A+0.2B → 1.8B=2.2A → B=2.2/1.8 A
    a = Decimal(100)
    b = a * Decimal("2.2") / Decimal("1.8")  # D == 0.2
    r = compare_estimates(est(a), est(b))
    assert r.status == "close"

    b2 = a * Decimal("2.3") / Decimal("1.7")  # D > 0.2
    r2 = compare_estimates(est(a), est(b2))
    assert r2.status == "review_required"
