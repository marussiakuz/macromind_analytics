"""Fund profile + industry settings shared across specializations (2026-10-22).

Same RAG infrastructure for any fund vertical (chemistry, logistics, RPA, …).
Only product/industry parameters change — not the evidence/validation rules.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IndustrySettings:
    code: str  # chemistry | logistics | rpa | fintech | ...
    label: str
    # query vocabulary (added to product terms)
    ru_terms: list[str] = field(default_factory=list)
    en_terms: list[str] = field(default_factory=list)
    # what is a "hard" metric in this industry (units that must be checked)
    metric_units: list[str] = field(default_factory=list)
    # never infer market growth from these alone
    non_growth_signals: list[str] = field(default_factory=lambda: [
        "publications", "citations", "hires", "press_mentions",
    ])
    # required for a competitor claim
    competitor_signals: list[str] = field(default_factory=lambda: [
        "same_product", "same_buyers", "same_use_case",
    ])


@dataclass
class FundProfile:
    fund_id: str
    name: str
    workspaces: list[str] = field(default_factory=list)
    industry: str = "general"
    geography: str = "Россия"
    focus_products: list[str] = field(default_factory=list)
    # ACL: which principals/workspaces this fund's analysts may read
    allowed_workspaces: list[str] = field(default_factory=list)
    # quality policy
    require_number_in_evidence: bool = True
    refuse_on_insufficient_data: bool = True
    min_evidence_for_fact: int = 1
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FundProfile":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


# Built-in industry presets (shared, not fund-specific logic)
INDUSTRIES: dict[str, IndustrySettings] = {
    "chemistry": IndustrySettings(
        code="chemistry",
        label="Химия / химические проекты",
        ru_terms=["химическая промышленность", "химпроизводство", "полимеры", "удобрения", "спецхимия"],
        en_terms=["chemical industry", "specialty chemicals", "polymers", "fertilizers"],
        metric_units=["т", "тонн", "kt", "млн т", "млрд руб", "млрд $", "%", "CAGR", "°C", "бар"],
    ),
    "logistics": IndustrySettings(
        code="logistics",
        label="Логистика / грузоперевозки",
        ru_terms=["грузоперевозки", "логистика", "складская сеть", "last mile"],
        en_terms=["freight", "logistics", "warehouse", "last mile"],
        metric_units=["т-км", "млрд руб", "%", "рейс"],
    ),
    "rpa": IndustrySettings(
        code="rpa",
        label="RPA / автоматизация",
        ru_terms=["роботизация процессов", "RPA", "автоматизация бизнес-процессов"],
        en_terms=["robotic process automation", "RPA", "process mining"],
        metric_units=["%", "ROI", "мес", "FTE"],
    ),
    "general": IndustrySettings(
        code="general",
        label="Общая",
        ru_terms=["рынок", "исследование", "отчет"],
        en_terms=["market research", "report"],
        metric_units=["%", "млрд"],
    ),
}


def industry_for(code: str | None) -> IndustrySettings:
    return INDUSTRIES.get((code or "general").lower(), INDUSTRIES["general"])


def load_fund_profile(path: str | Path) -> FundProfile:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FundProfile.from_dict(data)


def save_fund_profile(profile: FundProfile, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def merge_doc_metadata(*parts: dict | None) -> dict:
    """Document metadata: provenance + industry + read_level + limitations."""
    out: dict[str, Any] = {}
    for p in parts:
        if p:
            out.update({k: v for k, v in p.items() if v is not None})
    return out


def standard_doc_metadata(
    *,
    source: str,
    read_level: str = "abstract_only",
    industry: str = "general",
    doi: str | None = None,
    original_url: str | None = None,
    claim_type: str = "lead",
    extra: dict | None = None,
) -> dict[str, Any]:
    return merge_doc_metadata({
        "source": source,
        "read_level": read_level,
        "industry": industry,
        "doi": doi,
        "original_url": original_url,
        "claim_type": claim_type,
        "research_lead": claim_type in {"lead", "opinion"},
    }, extra)
