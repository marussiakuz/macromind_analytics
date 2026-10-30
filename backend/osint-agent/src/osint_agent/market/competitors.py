"""Competitor selection, features and VRIO (plan §12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class VRIOAnswer(str, Enum):
    yes = "yes"
    no = "no"
    unknown = "unknown"
    conflicting = "conflicting"


class CompetitorKind(str, Enum):
    direct = "direct"
    substitute = "substitute"
    inhouse = "inhouse"


class Competitor(BaseModel):
    """Компания и продукт хранятся раздельно (plan §12)."""

    id: UUID = Field(default_factory=uuid4)
    company_name: str
    product_name: str
    kind: CompetitorKind = CompetitorKind.direct
    identifiers: dict[str, str] = Field(default_factory=dict)
    market: str | None = None
    inclusion_reason: str | None = None
    confirmed: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None


class FeatureAssessment(BaseModel):
    competitor_id: UUID
    feature: str
    value_numeric: Decimal | None = None
    unit: str | None = None
    value_scale: str | None = None
    evidence: str | None = None
    author: str = "analyst"

    @field_validator("value_numeric", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        if v is None or v == "":
            return None
        return Decimal(str(v))


class VRIOCell(BaseModel):
    answer: VRIOAnswer
    evidence: str | None = None
    explanation: str | None = None


class VRIOAssessment(BaseModel):
    competitor_id: UUID
    resource: str
    v: VRIOCell
    r: VRIOCell
    i: VRIOCell
    o: VRIOCell
    uncertainty: str | None = None


# Осторожные выводы (plan §12 VRIO), не доказательство коммерческого успеха
def interpret_vrio(a: VRIOAssessment) -> str:
    vals = (a.v.answer, a.r.answer, a.i.answer, a.o.answer)
    if vals[0] == VRIOAnswer.no:
        return "Ценность данного ресурса для выбранной задачи не подтверждается оценкой"
    if vals[0] == VRIOAnswer.yes and vals[1] == VRIOAnswer.no:
        return "Ресурс не обеспечивает редкость в рассмотренной группе"
    if all(x == VRIOAnswer.yes for x in vals):
        return "Предпосылки потенциально устойчивого преимущества"
    if vals[:3] == (VRIOAnswer.yes, VRIOAnswer.yes, VRIOAnswer.no) and vals[3] == VRIOAnswer.yes:
        return "Возможное временное преимущество"
    if vals[:3] == (VRIOAnswer.yes, VRIOAnswer.yes, VRIOAnswer.yes) and vals[3] in (
        VRIOAnswer.no,
        VRIOAnswer.unknown,
        VRIOAnswer.conflicting,
    ):
        return "Есть предпосылки, но использование ресурса организацией не подтверждено"
    return "Недостаточно данных для выбранного вывода"


def select_competitors(
    candidates: list[dict[str, Any]],
    *,
    target_count: int = 6,
) -> tuple[list[Competitor], list[Competitor]]:
    """Возвращает (включённые, исключённые). Не выдумывает недостающих (plan §12).

    Цель 5–7; если меньше — показать фактическое число и неполноту.
    """
    included: list[Competitor] = []
    excluded: list[Competitor] = []
    for raw in candidates:
        try:
            comp = Competitor.model_validate(raw)
        except Exception:
            continue
        if comp.excluded:
            excluded.append(comp)
        elif len(included) < target_count:
            included.append(comp)
        else:
            comp.excluded = True
            comp.exclusion_reason = "Сверх лимита отбора"
            excluded.append(comp)
    return included, excluded


def competitor_table(
    competitors: list[Competitor],
    features: list[FeatureAssessment],
) -> list[dict[str, Any]]:
    """Сводная таблица: признаки по конкурентам; «по запросу» — не 0."""
    by_c: dict[str, dict[str, Any]] = {}
    for c in competitors:
        by_c[str(c.id)] = {
            "competitor_id": str(c.id),
            "company_name": c.company_name,
            "product_name": c.product_name,
            "kind": c.kind.value,
            "features": {},
        }
    for f in features:
        key = str(f.competitor_id)
        if key not in by_c:
            continue
        by_c[key]["features"][f.feature] = {
            "value": None if f.value_numeric is None else format(f.value_numeric, "f"),
            "unit": f.unit,
            "scale": f.value_scale,
            "evidence": f.evidence,
        }
    return list(by_c.values())


@dataclass
class CompetitorFindings:
    included: list[Competitor] = field(default_factory=list)
    excluded: list[Competitor] = field(default_factory=list)
    incompleteness_note: str | None = None


def findings_summary(included: list[Competitor], excluded: list[Competitor]) -> CompetitorFindings:
    note = None
    if len(included) < 5:
        note = (
            f"Найдено {len(included)} подходящих конкурентов при цели 5–7; список неполный, "
            "недостающие не выдуманы."
        )
    return CompetitorFindings(included=included, excluded=excluded, incompleteness_note=note)
