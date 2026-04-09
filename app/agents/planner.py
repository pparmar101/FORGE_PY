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

CRITICAL — Tech Stack & File Path Rules:
- You will be given a REPOSITORY STRUCTURE snapshot showing the actual files and folders in the codebase.
- You MUST derive the tech stack, language, and framework from that structure — do NOT assume.
- All impacted file paths MUST use real paths that match the repository structure provided.
- If the repo contains .cs files → it is C#/.NET. Use C# namespaces and ASP.NET Web API patterns.
- If the repo contains .ts/.tsx files → it is TypeScript/React.
- If the repo contains .py files → it is Python.
- Never invent file paths. Every impacted file must exist in or be a logical addition to the repo structure shown.
- Follow existing naming conventions (e.g. if controllers are in Controllers/, put new controllers there).

CRITICAL — Minimise Changes / Reuse Before Creating:
- Before adding a new class, enum, or method, search the repo structure for an existing one to extend.
- If a feature (e.g. Publish) already exists, implement the inverse (e.g. Unpublish) by:
  (a) adding an enum value to the existing operation/status enum, and
  (b) adding a branch in the existing task processor — do NOT create a new processor.
- Do NOT add new ADC task types, registries, stored procedures, or gateway contracts unless
  the existing ones are provably insufficient for the new operation.
- Prefer adding a method to an existing service/controller over creating a new one.
- The number of impacted files should be the minimum necessary — avoid speculative changes.

Be precise and specific. Avoid vague steps. Your output will be used directly by a coding agent."""


class PlannerAgent(BaseAgent):
    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)

    async def run(self, ticket: JiraTicket, repo_structure: str = "", rag_context: str = "") -> PlannerOutput:
        user_content = _format_ticket(ticket, repo_structure, rag_context)
        return await self._call_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=PlannerOutput,
        )


def _format_ticket(ticket: JiraTicket, repo_structure: str = "", rag_context: str = "") -> str:
    comments_section = (
        "\n".join(f"- {c}" for c in ticket.comments)
        if ticket.comments
        else "No comments."
    )
    labels = ", ".join(ticket.labels) if ticket.labels else "None"

    repo_section = ""
    if repo_structure:
        repo_section = f"""
## Repository Structure
Use the following repo file tree to determine tech stack and derive correct file paths:

```
{repo_structure}
```
"""

    rag_section = ""
    if rag_context:
        rag_section = f"""
## Existing Related Code (retrieved from repo)
The following code snippets are the most semantically relevant to this ticket.
Use them to understand EXACTLY how similar features are already implemented —
mirror their patterns, reuse their classes/enums/services, and avoid duplicating logic.

{rag_context}
"""

    return f"""Jira Ticket: {ticket.ticket_id}
Type: {ticket.issue_type} | Priority: {ticket.priority} | Status: {ticket.status}
Assignee: {ticket.assignee or "Unassigned"} | Labels: {labels}

## Summary
{ticket.summary}

## Description
{ticket.description}

## Comments
{comments_section}
{repo_section}{rag_section}
Analyze this ticket and produce the full engineering plan as specified."""
