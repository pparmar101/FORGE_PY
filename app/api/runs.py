from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.models.orchestrator import RunState, RunStatus

router = APIRouter()


class StartRunRequest(BaseModel):
    ticket_id: str


class StartRunResponse(BaseModel):
    run_id: str
    status: str


@router.post("/runs", response_model=StartRunResponse)
async def start_run(request: Request, body: StartRunRequest) -> StartRunResponse:
    settings = get_settings()
    run_id = str(uuid.uuid4())

    state = RunState(
        run_id=run_id,
        ticket_id=body.ticket_id,
        status=RunStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    queue: asyncio.Queue = asyncio.Queue()

    request.app.state.runs[run_id] = state
    request.app.state.queues[run_id] = queue

    from app.orchestrator.forge_orchestrator import ForgeOrchestrator
    orchestrator = ForgeOrchestrator(settings)

    asyncio.create_task(orchestrator.run(body.ticket_id, state, queue))

    return StartRunResponse(run_id=run_id, status=RunStatus.PENDING.value)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> RunState:
    state: RunState | None = request.app.state.runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return state


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    state: RunState | None = request.app.state.runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    queue: asyncio.Queue = request.app.state.queues.get(run_id)

    return StreamingResponse(
        _event_generator(state, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_generator(
    state: RunState, queue: asyncio.Queue | None
) -> AsyncGenerator[str, None]:
    # Replay already-received events
    replayed = list(state.events)
    for event in replayed:
        yield _sse(event.model_dump_json())

    # If run is already complete/failed, stop here
    if state.status in (RunStatus.COMPLETE, RunStatus.FAILED):
        yield _sse('{"event_type": "stream_end"}')
        return

    # Drain replayed events from the queue to avoid sending them twice
    # (emit() puts every event in both state.events and the queue)
    for _ in range(len(replayed)):
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    # Tail new events from the queue
    if queue is None:
        return

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue

        if event is None:
            # Sentinel — orchestrator is done
            yield _sse('{"event_type": "stream_end"}')
            break

        yield _sse(event.model_dump_json())


def _sse(data: str) -> str:
    return f"data: {data}\n\n"
