"""Pydantic models for People Search."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# === Core Models ===

class Skill(BaseModel):
    """Навык с подтверждением."""
    name: str
    level: str | None = None  # junior/middle/senior/expert
    evidence: list[str] = []  # источники подтверждения
    years_experience: int | None = None


class Experience(BaseModel):
    """Место работы."""
    company: str
    position: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    source: str = ""


class Education(BaseModel):
    """Образование."""
    institution: str
    degree: str | None = None
    field: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    source: str = ""


class GitHubProfile(BaseModel):
    """GitHub профиль."""
    username: str
    bio: str | None = None
    company: str | None = None
    location: str | None = None
    blog: str | None = None
    public_repos: int = 0
    followers: int = 0
    following: int = 0
    top_languages: list[str] = []
    contributions_last_year: int | None = None
    notable_repos: list[dict[str, Any]] = []
    url: str = ""


class Publication(BaseModel):
    """Научная публикация."""
    title: str
    authors: list[str] = []
    year: int | None = None
    citations: int | None = None
    venue: str | None = None
    url: str | None = None


class Article(BaseModel):
    """Статья (блог, Habr, Medium, VC.ru)."""
    title: str
    url: str
    platform: str = ""
    date: str | None = None
    views: int | None = None
    tags: list[str] = []


class Book(BaseModel):
    """Книга."""
    title: str
    authors: list[str] = []
    year: int | None = None
    publisher: str | None = None
    isbn: str | None = None


class SocialProfile(BaseModel):
    """Социальный профиль."""
    platform: str
    url: str
    username: str | None = None
    name: str | None = None
    city: str | None = None
    workplace: str | None = None
    education: str | None = None
    is_public: bool = True
    source: str = ""


class PersonConnection(BaseModel):
    """Связь между людьми."""
    person_name: str
    relationship: str  # "colleague", "co-author", "co-founder", "friend"
    evidence: str = ""
    source: str = ""


class RedFlag(BaseModel):
    """Red flag для физлица."""
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # sanctions, courts, fssp, news, cv_mismatch, lifestyle
    description: str
    evidence: dict[str, Any] = {}
    source: str = ""


class CandidateMatch(BaseModel):
    """Кандидат при disambiguation — промежуточный результат."""
    full_name: str
    match_score: float = 0  # 0-100 (scoring из совпадений)
    matched_fields: list[str] = []  # ["name", "company", "city"]
    current_position: str | None = None
    current_company: str | None = None
    city: str | None = None
    skills_preview: list[str] = []  # топ-5 навыков
    found_sources: list[str] = []  # ["linkedin", "habr", "github"]
    photo_url: str | None = None
    profile_id: str | None = None  # для загрузки полного профиля
    selected_accounts: dict[str, str] = Field(default_factory=dict)
    is_demo: bool = False


class CompetenceAssessment(BaseModel):
    """Оценка компетенций."""
    person_name: str
    overall_score: float = 0  # 0-100
    technical_score: float | None = None
    experience_score: float | None = None
    reputation_score: float | None = None
    strengths: list[str] = []
    concerns: list[str] = []
    evidence_summary: str = ""


# === Main Profile ===

class PersonProfile(BaseModel):
    """Полный профиль человека."""
    id: str = Field(default_factory=lambda: str(uuid4()))

    # Идентификация
    full_name: str | None = None
    nicknames: list[str] = []
    name_variants: list[str] = []  # транслитерации, сокращения

    # Социальные профили
    social_profiles: list[SocialProfile] = []

    # Навыки и компетенции
    skills: list[Skill] = []
    programming_languages: list[str] = []

    # Карьера
    experience: list[Experience] = []
    education: list[Education] = []
    current_position: str | None = None
    current_company: str | None = None

    # Публичная активность
    github: GitHubProfile | None = None
    publications: list[Publication] = []
    articles: list[Article] = []
    books: list[Book] = []

    # OSINT проверки
    is_sanctioned: bool | None = None
    sanction_matches: list[dict[str, Any]] = []
    is_pep: bool | None = None
    court_cases: list[dict[str, Any]] = []
    enforcement_proceedings: list[dict[str, Any]] = []
    news_mentions: list[dict[str, Any]] = []

    # Связи
    connections: list[PersonConnection] = []
    mutual_friends: list[str] = []

    # Оценка
    competence_score: float | None = None
    competence_assessment: CompetenceAssessment | None = None
    red_flags: list[RedFlag] = []
    sources: list[str] = []  # откуда взяты данные

    # Метаданные
    is_demo: bool = False
    source_statuses: dict[str, str] = Field(default_factory=dict)
    source_details: dict[str, str] = Field(default_factory=dict)
    searched_at: datetime = Field(default_factory=datetime.utcnow)
    search_duration_ms: float | None = None


# === Connector I/O ===

class ConnectorQuery(BaseModel):
    """Query to be sent to a connector."""
    query_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"


class ConnectorResult(BaseModel):
    """Result from a connector."""
    success: bool
    data: dict[str, Any] | None = None
    source: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = 1.0
    error: str | None = None
    # Stable machine-readable code: missing_api_key | provider_error | ...
    error_code: str | None = None
