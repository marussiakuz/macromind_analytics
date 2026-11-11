"""Compare extracted facts with a hand-made reference. Used by scripts/pitchdeck_lab.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from osint_agent.pitchdeck.models import FactStatus
from osint_agent.pitchdeck.normalize import parse_value, parse_years, same_amount


# The slide does not say whether the value is achieved or planned, so any status is accepted.
ANY_STATUS = "any"


@dataclass(frozen=True)
class GoldFact:
    slide: int
    metric: str
    amount: float | None
    years: tuple[int, ...]
    status: str
    entity: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoldFact":
        parsed = parse_value(str(data["value"]), str(data.get("unit", "")))
        return cls(
            slide=int(data["slide"]),
            metric=str(data["metric"]),
            amount=parsed.amount,
            years=tuple(parse_years(str(data.get("period", "")))),
            status=str(data.get("status", FactStatus.unknown.value)),
            entity=str(data.get("entity", "")).strip().lower(),
        )


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        total = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / total if total else 0.0

    def add(self, other: "Score") -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
        }


_LOOKALIKES = str.maketrans("асеорхуіткмнв", "aceopxyitkmhb")


def _entity_matches(gold: str, predicted: str) -> bool:
    if not gold:
        return True
    predicted = predicted.strip().lower().translate(_LOOKALIKES)
    if not predicted:
        return False
    # A reference may list alternative names separated by "|".
    options = [o.strip().translate(_LOOKALIKES) for o in gold.split("|")]
    return any(o in predicted or predicted in o for o in options)


def facts_match(gold: GoldFact, pred: dict[str, Any], *, strict: bool) -> bool:
    """Relaxed: same slide, metric and number. Strict also needs period, status and entity."""
    if gold.slide != pred["slide"] or gold.metric != pred["metric"]:
        return False
    if not same_amount(gold.amount, pred.get("amount")):
        return False
    if not strict:
        return True
    return (
        gold.years == tuple(pred.get("years") or ())
        and gold.status in {ANY_STATUS, pred.get("status")}
        and _entity_matches(gold.entity, pred.get("entity", ""))
    )


def score_deck(golds: list[GoldFact], preds: list[dict[str, Any]], *, strict: bool) -> tuple[Score, list[int]]:
    """One-to-one greedy match. Returns the score and indexes of matched predictions."""
    used: set[int] = set()
    tp = 0
    for gold in golds:
        for index, pred in enumerate(preds):
            if index not in used and facts_match(gold, pred, strict=strict):
                used.add(index)
                tp += 1
                break
    return Score(tp=tp, fp=len(preds) - tp, fn=len(golds) - tp), sorted(used)
