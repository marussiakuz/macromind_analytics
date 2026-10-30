"""Triangulation: comparability checks and divergence metric (plan §10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from osint_agent.market.models import Estimate, EstimateKind


class TriangulationError(ValueError):
    def __init__(self, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or []


@dataclass(frozen=True)
class TriangulationResult:
    status: str  # close | review_required | divergent | both_zero | not_comparable | insufficient_data | shared_evidence
    divergence: Decimal | None
    message: str
    reasons: list[str] = field(default_factory=list)
    a_kind: str | None = None
    b_kind: str | None = None


# Пороги внутренние, не научный норматив (plan §10)
CLOSE_MAX = Decimal("0.20")
REVIEW_MAX = Decimal("0.30")

_COMPARABLE_FIELDS = (
    "measure_type",
    "geography",
    "period",
    "currency",
    "kind",
)


def classify_divergence(d: Decimal) -> str:
    if d <= CLOSE_MAX:
        return "close"
    if d <= REVIEW_MAX:
        return "review_required"
    return "divergent"


def _compatibility_reasons(a: Estimate, b: Estimate) -> list[str]:
    reasons: list[str] = []
    if a.measure_type != b.measure_type:
        reasons.append("measure_type")
    if a.geography != b.geography:
        reasons.append("geography")
    if (a.period or None) != (b.period or None):
        reasons.append("reference_period")
    if a.currency != b.currency:
        reasons.append("currency")
    # Потенциал и спрос — разные показатели (plan §9)
    if a.kind != b.kind:
        reasons.append("kind")
    return reasons


def compare_estimates(
    a: Estimate | None,
    b: Estimate | None,
    *,
    shared_evidence: bool = False,
) -> TriangulationResult:
    """D = |A−B| / ((A+B)/2) для положительных сопоставимых оценок (plan §10)."""
    if a is None or b is None:
        return TriangulationResult(
            status="insufficient_data",
            divergence=None,
            message="Не хватает одной из оценок",
            reasons=["missing_estimate"],
        )

    reasons = _compatibility_reasons(a, b)
    if reasons:
        return TriangulationResult(
            status="not_comparable",
            divergence=None,
            message="Оценки несопоставимы",
            reasons=reasons,
            a_kind=a.kind.value,
            b_kind=b.kind.value,
        )

    av = a.value
    bv = b.value
    if av is None or bv is None:
        return TriangulationResult(
            status="insufficient_data",
            divergence=None,
            message="Неизвестное значение не заменяется нулём",
            reasons=["missing_value"],
        )

    # Оба нуля — без деления на ноль (C08)
    if av == 0 and bv == 0:
        return TriangulationResult(
            status="both_zero",
            divergence=None,
            message="Обе оценки подтверждены как нулевые; D не вычисляется",
            reasons=[],
            a_kind=a.kind.value,
            b_kind=b.kind.value,
        )

    denominator = (av + bv) / Decimal(2)
    if denominator == 0:
        # один ноль, второй с противоположным знаком — не наш случай денежных оценок
        return TriangulationResult(
            status="not_comparable",
            divergence=None,
            message="Знаменатель D равен нулю",
            reasons=["zero_mean"],
        )

    d = abs(av - bv) / abs(denominator)
    status = classify_divergence(d)
    if shared_evidence:
        status = "shared_evidence"
        message = "Общий первоисточник: независимость методов ограничена"
    elif status == "close":
        message = "Расхождение в пределах 20%"
    elif status == "review_required":
        message = "Расхождение 20–30%: требуется разбор"
    else:
        message = "Расхождение выше 30%"

    return TriangulationResult(
        status=status,
        divergence=d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        message=message,
        reasons=[],
        a_kind=a.kind.value,
        b_kind=b.kind.value,
    )
