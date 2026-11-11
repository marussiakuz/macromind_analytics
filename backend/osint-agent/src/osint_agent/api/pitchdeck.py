"""Pitch deck analysis API (prefix /api/v1/pitchdeck). Models run only on local Ollama."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from osint_agent.config import settings
from osint_agent.pitchdeck.ingest import DeckReadError, read_deck, sniff_kind
from osint_agent.pitchdeck.llm import LocalLLMError, OllamaClient
from osint_agent.pitchdeck.pipeline import analyze_deck
from osint_agent.pitchdeck.repository import PitchDeckRepository
from osint_agent.utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/pitchdeck", tags=["pitchdeck"])

_tasks: set[asyncio.Task] = set()
_gate = asyncio.Semaphore(1)
_repository: PitchDeckRepository | None = None


def get_repository() -> PitchDeckRepository:
    global _repository
    if _repository is None:
        _repository = PitchDeckRepository(Path(settings.pitchdeck_data_dir))
        _repository.fail_interrupted()
    return _repository


def build_client() -> OllamaClient:
    return OllamaClient(
        settings.pitchdeck_ollama_url,
        settings.pitchdeck_model,
        allow_remote=settings.pitchdeck_allow_remote_llm,
    )


async def run_analysis(analysis_id: str, repository: PitchDeckRepository, client: OllamaClient) -> None:
    async with _gate:
        path = repository.deck_path(analysis_id)
        record = repository.get(analysis_id)
        if path is None or record is None:
            await client.aclose()
            return
        try:
            raws = await asyncio.to_thread(read_deck, path)
            for raw in raws:
                if raw.image_png:
                    repository.slide_path(analysis_id, raw.number).write_bytes(raw.image_png)
            repository.set_progress(analysis_id, 0, len(raws))

            async def progress(done: int, total: int) -> None:
                repository.set_progress(analysis_id, done, total)

            result = await analyze_deck(
                path,
                client,
                filename=record["filename"],
                progress=progress,
                raw_slides=raws,
            )
            repository.set_done(analysis_id, result)
        except DeckReadError as exc:
            repository.set_failed(analysis_id, "unreadable_deck", str(exc))
        except LocalLLMError as exc:
            repository.set_failed(analysis_id, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - a job must always reach a final status
            logger.error("pitchdeck_failed", analysis_id=analysis_id, error=type(exc).__name__)
            repository.set_failed(analysis_id, "internal_error", "Внутренняя ошибка обработки")
        finally:
            await client.aclose()


def _valid_id(analysis_id: str) -> str:
    try:
        return str(UUID(analysis_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Анализ не найден") from exc


@router.get("/status")
async def model_status() -> dict[str, Any]:
    try:
        client = build_client()
    except LocalLLMError as exc:
        return {"available": False, "code": exc.code, "message": exc.message}
    try:
        return await client.health()
    except LocalLLMError as exc:
        return {"available": False, "code": exc.code, "message": exc.message, "model": client.model}
    finally:
        await client.aclose()


@router.post("/analyses", status_code=202)
async def create_analysis(file: UploadFile = File(...)) -> dict[str, Any]:
    limit = settings.pitchdeck_max_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"Файл больше {settings.pitchdeck_max_upload_mb} МБ")
    suffix = sniff_kind(content[:8])
    if suffix is None or Path(file.filename or "").suffix.lower() != suffix:
        raise HTTPException(status_code=415, detail="Поддерживаются только файлы PDF и PPTX")
    try:
        client = build_client()
    except LocalLLMError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    try:
        health = await client.health()
    except LocalLLMError as exc:
        await client.aclose()
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.message}) from exc
    if not health["model_installed"]:
        await client.aclose()
        raise HTTPException(
            status_code=503,
            detail={"code": "model_missing", "message": f"Модель {client.model} не установлена в Ollama"},
        )
    repository = get_repository()
    filename = Path(file.filename or "deck").name[:200]
    analysis_id = repository.create(filename, suffix, content)
    task = asyncio.create_task(run_analysis(analysis_id, repository, client))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"id": analysis_id, "status": "queued"}


@router.get("/analyses")
async def list_analyses(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    return get_repository().list(limit)


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str) -> dict[str, Any]:
    record = get_repository().get(_valid_id(analysis_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Анализ не найден")
    return record


@router.get("/analyses/{analysis_id}/slides/{number}/image")
async def get_slide_image(analysis_id: str, number: int) -> FileResponse:
    path = get_repository().slide_path(_valid_id(analysis_id), number)
    if number < 1 or not path.exists():
        raise HTTPException(status_code=404, detail="Изображение слайда недоступно")
    return FileResponse(path, media_type="image/png")


@router.delete("/analyses/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: str) -> None:
    if not get_repository().delete(_valid_id(analysis_id)):
        raise HTTPException(status_code=404, detail="Анализ не найден")
