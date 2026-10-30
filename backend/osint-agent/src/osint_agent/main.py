"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from osint_agent.config import settings
from osint_agent.utils import setup_logging, get_logger
from osint_agent.utils.cache import cache
from osint_agent.api.graph import router as graph_router
from osint_agent.api.counterparties import router as counterparties_router
from osint_agent.api.persons import router as persons_router
from osint_agent.api.companies import router as companies_router
from osint_agent.api.market import router as market_router
from osint_agent.api.knowledge import router as knowledge_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    # Startup
    setup_logging(settings.log_level, settings.log_format)
    logger.info("starting", app=settings.app_name, env=settings.app_env)

    # Export .env keys into os.environ so Yandex/OpenAlex providers can see them
    try:
        from osint_agent.knowledge.env import apply_knowledge_env
        applied = apply_knowledge_env()
        logger.info("knowledge_env_applied", keys=sorted(applied.keys()))
    except Exception as e:  # noqa: BLE001
        logger.warning("knowledge_env_failed", error=str(e))

    # Connect to Redis
    try:
        await cache.connect()
        logger.info("redis_connected")
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))

    yield

    # Shutdown
    await cache.disconnect()
    logger.info("shutdown")


app = FastAPI(
    title="OSINT Agent",
    description="OSINT Agent for MacroMind Analytics — automated Pre-Due Diligence",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graph_router)
app.include_router(counterparties_router)
app.include_router(persons_router)
app.include_router(companies_router)
app.include_router(market_router)
app.include_router(knowledge_router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "osint-agent"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "osint-agent",
        "version": "0.1.0",
        "docs": "/docs",
    }


# TODO: Add OSINT endpoints
# @app.post("/api/v1/osint/check")
# async def start_check(request: OSINTRequest):
#     ...


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "osint_agent.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_debug,
    )
