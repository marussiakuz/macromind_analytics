"""Reproducible market sizing (plan §8–§9). Pure functions, no network."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from osint_agent.market.models import (
    Estimate,
    EstimateKind,
    EstimateMethod,
    ScenarioTriple,
    SegmentInput,
    TopDownInput,
)


class SizingError(ValueError):
    """Validation failure for sizing inputs."""

    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []


def _to_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SizingError("INVALID_NUMBER", f"Поле {field}: не число", [field]) from exc


def validate_segment(segment: SegmentInput | dict[str, Any]) -> SegmentInput:
    """Входные проверки сегмента (plan §9 «Входные проверки»)."""
    try:
        seg = segment if isinstance(segment, SegmentInput) else SegmentInput.model_validate(segment)
    except ValidationError as exc:
        raise SizingError("INVALID_SEGMENT", "Некорректный сегмент", [e["loc"][-1] for e in exc.errors()]) from exc
    if seg.spend_includes_nonbuyers and seg.p_buy is not None:
        raise SizingError(
            "DOUBLE_COUNT",
            "Средние расходы уже включают непокупателей — повторное умножение на P запрещено",
            ["p_buy"],
        )
    return seg


def top_down(
    base: Any,
    shares: list[Any],
    *,
    currency: str = "RUB",
    geography: str = "RF",
    measure_type: str = "revenue",
    period: str | None = None,
) -> Estimate:
    """M_TD = M_base × s_1 × … × s_k (plan §8).

    Доли — в [0, 1]. Темпы роста/курсы здесь не поддерживаются: отдельный тип.
    """
    try:
        parsed = TopDownInput.model_validate({"base": base, "shares": shares})
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        raise SizingError(
            "INVALID_TOP_DOWN",
            str(first.get("msg", "Некорректные входы сверху вниз")),
            [str(x) for x in first.get("loc", [])],
        ) from exc

    value = parsed.base
    log = [f"M_base={parsed.base}"]
    for i, share in enumerate(parsed.shares, start=1):
        value *= share
        log.append(f"× s_{i}={share} → {value}")

    return Estimate(
        method=EstimateMethod.top_down,
        kind=EstimateKind.potential,
        measure_type=measure_type,
        geography=geography,
        currency=currency,
        period=period,
        formula="M_TD = M_base × s_1 × … × s_k",
        value=value,
        unit="currency/year",
        limitations=[],
        status="computed",
        log=log,
    )


def _segment_potential(seg: SegmentInput) -> Decimal:
    return Decimal(seg.n_eligible) * seg.acv_potential


def _segment_demand(seg: SegmentInput) -> Decimal:
    if seg.spend_includes_nonbuyers:
        raise SizingError(
            "DOUBLE_COUNT",
            "Средние расходы уже включают непокупателей — не умножать на P",
            [seg.name, "p_buy"],
        )
    if seg.p_buy is None:
        raise SizingError("MISSING_P", f"Сегмент {seg.name}: не указана доля P", [seg.name, "p_buy"])
    if seg.acv_buyers is None:
        raise SizingError("MISSING_ACVP", f"Сегмент {seg.name}: нет ACV покупателей", [seg.name, "acv_buyers"])
    return Decimal(seg.n_eligible) * seg.p_buy * seg.acv_buyers


def bottom_up_potential(
    segments: list[SegmentInput | dict[str, Any]],
    *,
    currency: str = "RUB",
    geography: str = "RF",
    measure_type: str = "revenue",
    period: str | None = None,
) -> Estimate:
    """Potential = Σ N_eligible,h × ACV_potential,h (plan §9)."""
    parsed = [validate_segment(s) for s in segments]
    if not parsed:
        raise SizingError("EMPTY_SEGMENTS", "Нет сегментов для расчёта", ["segments"])
    total = Decimal(0)
    log: list[str] = []
    for seg in parsed:
        part = _segment_potential(seg)
        total += part
        log.append(f"{seg.name}: N={seg.n_eligible} × ACV_pot={seg.acv_potential} → {part}")
    log.append(f"Potential = {total}")
    return Estimate(
        method=EstimateMethod.bottom_up,
        kind=EstimateKind.potential,
        measure_type=measure_type,
        geography=geography,
        currency=currency,
        period=period,
        formula="Potential = Σ (N_eligible,h × ACV_potential,h)",
        value=total,
        unit="currency/year",
        status="computed",
        log=log,
    )


def bottom_up_demand(
    segments: list[SegmentInput | dict[str, Any]],
    *,
    currency: str = "RUB",
    geography: str = "RF",
    measure_type: str = "revenue",
    period: str | None = None,
) -> Estimate:
    """Demand = Σ N_eligible,h × P_h × ACV_buyers,h (plan §9)."""
    parsed = [validate_segment(s) for s in segments]
    if not parsed:
        raise SizingError("EMPTY_SEGMENTS", "Нет сегментов для расчёта", ["segments"])
    total = Decimal(0)
    log: list[str] = []
    for seg in parsed:
        part = _segment_demand(seg)
        total += part
        log.append(f"{seg.name}: N={seg.n_eligible} × P={seg.p_buy} × ACV_b={seg.acv_buyers} → {part}")
    log.append(f"Demand = {total}")
    return Estimate(
        method=EstimateMethod.bottom_up,
        kind=EstimateKind.demand,
        measure_type=measure_type,
        geography=geography,
        currency=currency,
        period=period,
        formula="Demand = Σ (N_eligible,h × P_h × ACV_buyers,h)",
        value=total,
        unit="currency/year",
        status="computed",
        log=log,
    )


def sensitivity_base(
    base_acv: Decimal,
    n: int,
    low_acv: Decimal,
    high_acv: Decimal,
    *,
    p: Decimal | None = None,
) -> ScenarioTriple:
    """Чувствительность по ACV: один вход между границами (plan §10). C14.

    Это сценарии, не доверительный интервал.
    """
    if low_acv > high_acv:
        raise SizingError("INVALID_RANGE", "low_acv > high_acv", ["low_acv", "high_acv"])
    if n < 0:
        raise SizingError("INVALID_N", "N неотрицателен", ["n"])
    factor = Decimal(n) if p is None else Decimal(n) * p
    return ScenarioTriple(low=low_acv * factor, base=base_acv * factor, high=high_acv * factor)
