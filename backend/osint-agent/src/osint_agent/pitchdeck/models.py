"""Data models for pitch deck analysis."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Metric(str, Enum):
    revenue = "revenue"
    expenses = "expenses"
    ebitda = "ebitda"
    net_profit = "net_profit"
    market_tam = "market_tam"
    market_sam = "market_sam"
    market_som = "market_som"
    market_size = "market_size"
    market_share = "market_share"
    customer_share = "customer_share"
    growth_rate = "growth_rate"
    headcount = "headcount"
    customers = "customers"
    investment_ask = "investment_ask"
    investment_raised = "investment_raised"
    valuation = "valuation"
    other = "other"


class FactStatus(str, Enum):
    fact = "fact"
    forecast = "forecast"
    target = "target"
    unknown = "unknown"


class Verdict(str, Enum):
    correct = "correct"
    wrong = "wrong"
    unsure = "unsure"
    not_run = "not_run"


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class FlagKind(str, Enum):
    numeric = "numeric"
    claim = "claim"
    coverage = "coverage"


class Slide(BaseModel):
    number: int
    text: str = ""
    has_image: bool = False
    skipped: bool = False
    error: str | None = None


class DeckFact(BaseModel):
    """A claim made by the applicant on a slide. It is not independently verified."""

    id: str
    slide: int
    metric: Metric
    label: str = ""
    value_raw: str
    unit_raw: str = ""
    period_raw: str = ""
    entity: str = ""
    status: FactStatus = FactStatus.unknown
    quote: str = ""
    amount: float | None = None
    amount_high: float | None = None
    unit_kind: str = "other"
    years: list[int] = Field(default_factory=list)
    value_in_text: bool = False
    verdict: Verdict = Verdict.not_run
    needs_review: bool = True


class DeckEntity(BaseModel):
    """A name found in slide text. A candidate for an analyst, not a verified link."""

    kind: str  # organization, person, inn or ogrn
    text: str
    slides: list[int] = Field(default_factory=list)
    mentions: int = 0


class RedFlag(BaseModel):
    rule: str
    severity: Severity
    kind: FlagKind
    title: str
    detail: str
    slides: list[int] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class DeckSummary(BaseModel):
    text: str
    generated_by: str  # "llm" or "template"
    note: str = ""


class DeckAnalysis(BaseModel):
    filename: str = ""
    slide_count: int = 0
    slides: list[Slide] = Field(default_factory=list)
    facts: list[DeckFact] = Field(default_factory=list)
    entities: list[DeckEntity] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)
    summary: DeckSummary | None = None
    model: str = ""
    input_mode: str = "text+image"
    limitations: list[str] = Field(default_factory=list)
