from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, runs
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # In-memory run store: run_id → RunState
    app.state.runs = {}
    # Per-run asyncio queues for SSE streaming: run_id → asyncio.Queue
    app.state.queues = {}

    # Validate config on startup — raises if required env vars are missing
    settings = get_settings()
    app.state.settings = settings

    yield

    # Cleanup (nothing to do for in-memory store)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="FORGE",
        description="Fully Orchestrated Retrieval Augmented & Generation Engine: Jira → Plan → Code → Review → PR",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(runs.router)

    return app


app = create_app()
