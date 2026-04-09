from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.coder import CoderOutput
from app.models.planner import PlannerOutput
from app.models.reviewer import ReviewerOutput


class RunStatus(str, Enum):
    PENDING = "pending"
    FETCHING_TICKET = "fetching_ticket"
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    APPLYING = "applying"
    CREATING_PR = "creating_pr"
    COMPLETE = "complete"
    FAILED = "failed"


class RunEvent(BaseModel):
    event_type: Literal[
        "status_change", "agent_complete", "error", "run_complete", "ticket_fetched"
    ]
    agent: Literal["planner", "coder", "reviewer", "system"] | None = None
    status: RunStatus | None = None
    payload: dict | None = None
    iteration: int = 1
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RunState(BaseModel):
    run_id: str
    ticket_id: str
    status: RunStatus = RunStatus.PENDING
    ticket: dict | None = None
    iteration: int = 1
    planner_output: PlannerOutput | None = None
    coder_output: CoderOutput | None = None
    reviewer_output: ReviewerOutput | None = None
    pr_url: str | None = None
    branch_name: str | None = None
    error: str | None = None
    events: list[RunEvent] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
