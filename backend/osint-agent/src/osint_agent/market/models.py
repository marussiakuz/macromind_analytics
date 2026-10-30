"""Checked structures for market research (plan §6).

Money values are Decimal in memory and strings in JSON to keep precision.
Missing values are None — never 0.0 as a substitute for unknown.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObservationStatus(str, Enum):
    unreviewed = "unreviewed"
    verified = "verified"
    rejected = "rejected"
    conflicting = "conflicting"


class EstimateMethod(str, Enum):
    top_down = "top_down"
    bottom_up = "bottom_up"
    expert = "expert"


class EstimateKind(str, Enum):
    """Potencial (упражнение на объём) и спрос — разные показатели (plan §9)."""
    potential = "potential"
    demand = "demand"


class VRIOAnswer(str, Enum):
    yes = "yes"
    no = "no"
    unknown = "unknown"
    conflicting = "conflicting"


class Money(BaseModel):
    """Денежное значение: amount + currency + scale + price/tax basis."""

    amount: Decimal | None = None
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217, например RUB")
    scale: str = Field(default="unit", description="unit | thousand | million | billion")
    price_basis: str | None = None
    tax_basis: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("amount must be a decimal number") from exc

    def scaled_amount(self) -> Decimal | None:
        """Расчётная сумма в единицах (без учёта налоговой/ценовой базы)."""
        if self.amount is None:
            return None
        multipliers = {
            "unit": Decimal(1),
            "thousand": Decimal(1_000),
            "million": Decimal(1_000_000),
            "billion": Decimal(1_000_000_000),
        }
        return self.amount * multipliers[self.scale]

    def json_amount(self) -> str | None:
        return None if self.amount is None else format(self.amount, "f")


class MarketScope(BaseModel):
    """Границы рынка продукта (plan §6 MarketScope)."""

    product: str
    customer_job: str | None = None
    buyer: str | None = None
    payer: str | None = None
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    reference_period: str | None = None
    measure_type: str = Field(
        default="revenue",
        description="revenue | added_value | volume — смешивание блокирует триангуляцию",
    )
    buyer_unit: str | None = None


class StudyPassport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    scope: MarketScope
    owner: str = "local"
    created_at: datetime = Field(default_factory=_utc_now)
    as_of: date | None = None
    version: int = 1
    money_basis_currency: str = "RUB"
    notes: str | None = None


class Observation(BaseModel):
    """Наблюдение из источника с точной ссылкой (plan §6)."""

    id: UUID = Field(default_factory=uuid4)
    metric: str
    value: Decimal | None = None
    unit: str
    geography: str | None = None
    reference_period: str | None = None
    source_id: str
    source_locator: str | None = None
    status: ObservationStatus = ObservationStatus.unreviewed
    captured_at: datetime = Field(default_factory=_utc_now)

    @field_validator("value", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("value must be a decimal number") from exc


class Assumption(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    unit: str
    meaning: str
    author: str = "analyst"
    rationale: str | None = None
    scenario: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("value", "low", "high", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("must be a decimal number") from exc


class CalculationInput(BaseModel):
    source_type: str = Field(description="observation | assumption | manual")
    source_id: UUID | None = None
    transform: str | None = None
    unit_out: str | None = None


class Estimate(BaseModel):
    method: EstimateMethod
    kind: EstimateKind
    measure_type: str
    geography: str
    currency: str
    period: str | None = None
    formula: str
    inputs: list[CalculationInput] = Field(default_factory=list)
    value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    unit: str = "currency/year"
    limitations: list[str] = Field(default_factory=list)
    status: str = "draft"
    log: list[str] = Field(default_factory=list)

    @field_validator("value", "low", "high", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("must be a decimal number") from exc


class SegmentInput(BaseModel):
    """Непересекающийся сегмент нижней оценки (plan §9)."""

    name: str
    n_eligible: int = Field(ge=0)
    acv_potential: Decimal = Field(ge=0)
    p_buy: Decimal | None = Field(default=None, ge=0, le=1)
    acv_buyers: Decimal | None = Field(default=None, ge=0)
    # True — средние расходы уже включают непокупателей (запрет P)
    spend_includes_nonbuyers: bool = False

    @field_validator("acv_potential", "acv_buyers", "p_buy", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("must be a decimal number") from exc

    @model_validator(mode="after")
    def _check_p_buy(self) -> "SegmentInput":
        if self.p_buy is not None and not (Decimal(0) <= self.p_buy <= Decimal(1)):
            raise ValueError("p_buy must be in [0, 1]")
        return self


class ScenarioTriple(BaseModel):
    """Нижний / базовый / верхний сценарий — не ДИ (plan §10)."""

    low: Decimal | None = None
    base: Decimal | None = None
    high: Decimal | None = None

    @field_validator("low", "base", "high", mode="before")
    @classmethod
    def _decimal(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("must be a decimal number") from exc


class TopDownInput(BaseModel):
    base: Decimal = Field(gt=0)
    shares: list[Decimal] = Field(min_length=1)

    @field_validator("shares", mode="before")
    @classmethod
    def _shares(cls, value: Any) -> list[Decimal]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("shares must be a list")
        out: list[Decimal] = []
        for item in value:
            try:
                out.append(Decimal(str(item)))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError("share must be a decimal") from exc
        return out

    @field_validator("shares")
    @classmethod
    def _range(cls, shares: list[Decimal]) -> list[Decimal]:
        for s in shares:
            if s < 0 or s > 1:
                raise ValueError("share must be in [0, 1] when it is a share")
        return shares
