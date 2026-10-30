"""Delphi expert rounds (plan §11). Manual entry / import; no fake experts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class RoundStatus(str, Enum):
    open = "open"
    closed = "closed"


class ExpertResponse(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    participant: str
    competency: str | None = None
    conflict_of_interest: str | None = None
    round_no: int = 1
    value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    explanation: str | None = None
    sources: list[str] = Field(default_factory=list)
    revision_reason: str | None = None
    supersedes: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("value", "low", "high", mode="before")
    @classmethod
    def _dec(cls, v: Any) -> Decimal | None:
        if v is None or v == "":
            return None
        return Decimal(str(v))


@dataclass
class DelphiRound:
    id: UUID
    study_id: str
    question: str
    unit: str
    status: RoundStatus = RoundStatus.open
    round_no: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    responses: list[ExpertResponse] = field(default_factory=list)
    # история правок координатором — новые записи, не стирание (plan §11)
    audit: list[str] = field(default_factory=list)


def add_response(round_: DelphiRound, response: ExpertResponse) -> ExpertResponse:
    """Раунд 1 независимый: чужие ответы не показываем до закрытия."""
    if response.round_no != round_.round_no:
        response.round_no = round_.round_no
    round_.responses.append(response)
    return response


def close_round(round_: DelphiRound) -> dict[str, Any]:
    if round_.status == RoundStatus.closed:
        return summarize(round_)
    round_.status = RoundStatus.closed
    round_.closed_at = datetime.now(timezone.utc)
    round_.audit.append(f"closed {round_.closed_at.isoformat()}")
    return summarize(round_)


def summarize(round_: DelphiRound) -> dict[str, Any]:
    """Медиана и разброс; при 3 участниках — все три значения (plan §11)."""
    values = [r.value for r in round_.responses if r.value is not None]
    participant_names = sorted({r.participant for r in round_.responses})
    out: dict[str, Any] = {
        "round_id": str(round_.id),
        "status": round_.status.value,
        "question": round_.question,
        "unit": round_.unit,
        "participants": participant_names,
        "participant_count": len(participant_names),
        "responses": [
            {
                "id": str(r.id),
                "participant": r.participant,
                "value": None if r.value is None else format(r.value, "f"),
                "low": None if r.low is None else format(r.low, "f"),
                "high": None if r.high is None else format(r.high, "f"),
                "explanation": r.explanation,
                "revision_reason": r.revision_reason,
                "round_no": r.round_no,
            }
            for r in round_.responses
        ],
    }
    if not values:
        out.update({"median": None, "spread": None, "note": "Нет числовых оценок"})
        return out
    med = median(values)
    out["median"] = format(med, "f")
    out["spread"] = format(max(values) - min(values), "f")
    if len(participant_names) == 1:
        out["note"] = "Оценка одного участника — панель не заявлена"
    elif len(values) <= 3:
        out["note"] = "Показаны все значения при малой панели"
    else:
        out["note"] = "Медиана и разброс по ответам"
    return out


def revise_response(round_: DelphiRound, original_id: UUID, new: ExpertResponse) -> ExpertResponse:
    """Правка координатором — новая запись с причиной, исходная сохраняется."""
    orig = next((r for r in round_.responses if r.id == original_id), None)
    if orig is None:
        raise KeyError(str(original_id))
    new.supersedes = original_id
    new.round_no = orig.round_no
    if not new.revision_reason:
        raise ValueError("revision_reason required")
    round_.responses.append(new)
    round_.audit.append(f"revise {original_id} -> {new.id}: {new.revision_reason}")
    return new
