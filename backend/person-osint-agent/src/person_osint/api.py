"""API endpoints для People Search."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from person_osint.search import get_people_search


router = APIRouter(prefix="/api/v1/people", tags=["people"])


class SearchRequest(BaseModel):
    """Запрос на поиск."""
    full_name: str
    nicknames: list[str] | None = None
    company: str | None = None
    position: str | None = None
    city: str | None = None
    skills: list[str] | None = None


class SelectRequest(BaseModel):
    """Выбор кандидата."""
    selected_accounts: dict[str, str] | None = None
    full_name: str
    nicknames: list[str] | None = None
    company: str | None = None
    position: str | None = None
    city: str | None = None
    skills: list[str] | None = None


@router.post("/search")
async def search_people(request: SearchRequest) -> dict[str, Any]:
    """Поиск кандидатов по ФИО + доп. поля.

    Возвращает список кандидатов для disambiguation.
    """
    if not request.full_name.strip():
        raise HTTPException(status_code=400, detail="full_name is required")

    tool = get_people_search()
    candidates = await tool.search_candidates(
        full_name=request.full_name,
        nicknames=request.nicknames,
        company=request.company,
        position=request.position,
        city=request.city,
        skills=request.skills,
    )

    return {
        "query": {
            "full_name": request.full_name,
            "company": request.company,
            "position": request.position,
            "city": request.city,
        },
        "total": len(candidates),
        "candidates": [c.model_dump() for c in candidates],
    }


@router.post("/profile")
async def get_profile(request: SelectRequest) -> dict[str, Any]:
    """Получить полный профиль кандидата.

    После выбора кандидата из /search.
    """
    if not request.full_name.strip():
        raise HTTPException(status_code=400, detail="full_name is required")

    tool = get_people_search()
    try:
        profile = await tool.get_full_profile(
            selected_accounts=request.selected_accounts,
            full_name=request.full_name,
            nicknames=request.nicknames,
            company=request.company,
            position=request.position,
            city=request.city,
            skills=request.skills,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return profile.model_dump()


@router.get("/{profile_id}")
async def get_profile_by_id(profile_id: str) -> dict[str, Any]:
    """Получить профиль по ID (заготовка)."""
    raise HTTPException(status_code=501, detail="Not implemented yet")
