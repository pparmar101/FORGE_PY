from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import BaseAgent
from app.models.jira import JiraTicket
from app.models.planner import PlannerOutput

if TYPE_CHECKING:
    from app.config import Settings

SYSTEM_PROMPT = """You are a Senior Tech Lead analyzing a Jira ticket to create a precise engineering plan.

Your job is to produce:
- DeveloperNotes: step-by-step implementation plan, impacted files (with change_type and reason), \
API changes, DB changes, edge cases, and assumptions.
- QANotes: positive/negative/regression test cases and regression risk areas.
- TaskBreakdown: ordered tasks with title, description, and complexity estimate.

Be precise and specific. Avoid vague steps. Your output will be used directly by a coding agent."""


class PlannerAgent(BaseAgent):
    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)

    async def run(self, ticket: JiraTicket) -> PlannerOutput:
        user_content = _format_ticket(ticket)
        return await self._call_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=PlannerOutput,
        )


def _format_ticket(ticket: JiraTicket) -> str:
    comments_section = (
        "\n".join(f"- {c}" for c in ticket.comments)
        if ticket.comments
        else "No comments."
    )
    labels = ", ".join(ticket.labels) if ticket.labels else "None"

    return f"""Jira Ticket: {ticket.ticket_id}
Type: {ticket.issue_type} | Priority: {ticket.priority} | Status: {ticket.status}
Assignee: {ticket.assignee or "Unassigned"} | Labels: {labels}

## Summary
{ticket.summary}

## Description
{ticket.description}

## Comments
{comments_section}

Analyze this ticket and produce the full engineering plan as specified."""
