"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from person_osint.api import router as people_router
from person_osint.api_checko import router as checko_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan."""
    yield


app = FastAPI(
    title="Person OSINT Agent",
    description="People Search — OSINT инструмент проверки людей",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(people_router)
app.include_router(checko_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "person-osint-agent"}
