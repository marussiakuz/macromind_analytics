"""Pydantic models for OSINT Agent."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# === Enums ===

class RedFlagPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RedFlagCategory(str, Enum):
    SANCTIONS = "sanctions"
    LEGAL = "legal"
    REPUTATION = "reputation"
    TEAM = "team"
    TECH = "tech"


class CompanyForm(str, Enum):
    OOO = "OOO"      # ООО
    ZAO = "ZAO"      # ЗАО
    AO = "AO"        # АО
    OAO = "OAO"      # ОАО
    PAO = "PAO"      # ПАО
    OTHER = "OTHER"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


# === Connector Models ===

class ConnectorQuery(BaseModel):
    """Query to be sent to a connector."""
    query_type: str  # "company_data", "court_cases", "sanctions", etc.
    params: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"


class ConnectorResult(BaseModel):
    """Result from a connector."""
    success: bool
    data: dict[str, Any] | None = None
    source: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    raw_response: Any = None
    error: str | None = None


# === Block Results ===

class CompanyData(BaseModel):
    """Company registration data from ЕГРЮЛ."""
    inn: str
    ogrn: str
    name: str
    full_name: str
    legal_form: str
    registration_date: datetime | None = None
    address: str = ""
    is_mass_address: bool = False
    okved_codes: list[str] = Field(default_factory=list)
    okved_main: str = ""
    charter_capital: float = 0.0
    status: str = "active"
    region_code: str = ""


class Shareholder(BaseModel):
    """Shareholder of a company."""
    type: str  # "person" or "company"
    name: str
    inn: str | None = None
    share_percent: float = 0.0
    depth: int = 0
    is_offshore: bool = False
    jurisdiction: str | None = None


class Director(BaseModel):
    """Director/manager of a company."""
    full_name: str
    inn: str | None = None
    position: str = ""
    is_disqualified: bool = False
    companies_count: int = 0
    is_mass_director: bool = False


class CourtCase(BaseModel):
    """Court case (arbitration or general jurisdiction)."""
    case_number: str
    court: str  # "arbitration" or "general"
    case_type: str
    status: str
    amount: float = 0.0
    plaintiff: str = ""
    defendant: str = ""
    date: datetime | None = None


class BailiffProduction(BaseModel):
    """Bailiff execution production."""
    production_number: str
    amount: float
    status: str
    date: datetime | None = None


class TenderInfo(BaseModel):
    """Government tender information."""
    tender_id: str
    status: str
    amount: float = 0.0
    participants_count: int = 0
    winner: str = ""
    is_single_source: bool = False


class SanctionMatch(BaseModel):
    """Match in sanctions registry."""
    registry: str  # "ofac", "eu", "uk", "un", "rosfin"
    name_matched: str
    name_original: str
    match_score: float
    details: dict[str, Any] = Field(default_factory=dict)


class SocialProfile(BaseModel):
    """Social network profile."""
    platform: str  # "vk", "facebook", "linkedin", etc.
    url: str
    name: str
    city: str | None = None
    workplace: str | None = None
    education: str | None = None
    birth_year: int | None = None
    friends_count: int | None = None
    is_public: bool = True


class NewsItem(BaseModel):
    """News article."""
    title: str
    url: str
    source: str
    date: datetime | None = None
    snippet: str = ""
    is_negative: bool = False


class PEPStatus(BaseModel):
    """Politically Exposed Person status."""
    is_pep: bool
    source: str
    details: str = ""


# === Block Results ===

class BlockAResult(BaseModel):
    """Block A — Юридическое лицо."""
    company: CompanyData
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockBResult(BaseModel):
    """Block B — Акционерная структура."""
    shareholders: list[Shareholder] = Field(default_factory=list)
    ultimate_beneficiary: Shareholder | None = None
    is_transparent: bool = True
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockCResult(BaseModel):
    """Block C — Менеджмент."""
    directors: list[Director] = Field(default_factory=list)
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockDResult(BaseModel):
    """Block D — Операционная деятельность."""
    court_cases: list[CourtCase] = Field(default_factory=list)
    bailiff_productions: list[BailiffProduction] = Field(default_factory=list)
    tenders: list[TenderInfo] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    website_age_days: int | None = None
    financial_data: dict[str, Any] = Field(default_factory=dict)
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockEResult(BaseModel):
    """Block E — Проверка физических лиц."""
    persons: list[dict[str, Any]] = Field(default_factory=list)
    sanction_matches: list[SanctionMatch] = Field(default_factory=list)
    pep_statuses: list[PEPStatus] = Field(default_factory=list)
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockFResult(BaseModel):
    """Block F — Социальные сети."""
    profiles: list[SocialProfile] = Field(default_factory=list)
    cv_mismatches: list[dict[str, Any]] = Field(default_factory=list)
    red_flags: list["RedFlag"] = Field(default_factory=list)


class BlockGResult(BaseModel):
    """Block G — Граф связей."""
    connections: list[dict[str, Any]] = Field(default_factory=list)
    graph_data: dict[str, Any] = Field(default_factory=dict)
    red_flags: list["RedFlag"] = Field(default_factory=list)


# === Red Flag ===

class RedFlag(BaseModel):
    """Red flag identified during OSINT check."""
    id: str
    priority: RedFlagPriority
    category: RedFlagCategory
    description: str
    block: str  # "A", "B", "C", "D", "E", "F", "G"
    evidence: dict[str, Any] = Field(default_factory=dict)
    source_ref: str = ""


# === Main Result ===

class OSINTResult(BaseModel):
    """Complete OSINT check result."""
    id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    inn: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Block results
    block_a: BlockAResult | None = None
    block_b: BlockBResult | None = None
    block_c: BlockCResult | None = None
    block_d: BlockDResult | None = None
    block_e: BlockEResult | None = None
    block_f: BlockFResult | None = None
    block_g: BlockGResult | None = None

    # Aggregated
    red_flags: list[RedFlag] = Field(default_factory=list)
    health_index: float = Field(ge=0.0, le=100.0, default=0.0)

    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_seconds: float | None = None


# === API Models ===

class OSINTRequest(BaseModel):
    """Request to start OSINT check."""
    company_id: UUID
    inn: str
    founders: list[str] = Field(default_factory=list)
    declared_activity: str = ""


class OSINTStatusResponse(BaseModel):
    """Response with OSINT check status."""
    job_id: UUID
    status: str  # "queued", "running", "completed", "failed"
    progress: float = Field(ge=0.0, le=100.0, default=0.0)
    result: OSINTResult | None = None
    error: str | None = None
