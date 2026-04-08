from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import BaseAgent
from app.models.coder import CoderOutput
from app.models.planner import PlannerOutput
from app.models.reviewer import ReviewerOutput

if TYPE_CHECKING:
    from app.config import Settings

SYSTEM_PROMPT = """You are a Staff Engineer performing a thorough code review.

You will receive:
1. An engineering plan (DeveloperNotes, QANotes, TaskBreakdown)
2. Proposed code changes (FileChanges, Tests, Commits)

Your job:
- Verify the implementation matches the plan.
- Identify bugs, edge cases missed, and code quality issues.
- Flag performance, security, and breaking-change risks.
- Decide: "Approve" if the code is production-ready, "Request Changes" if critical/major issues exist.
- Write a complete PR title and description ready to be submitted.

Be strict. Do not approve code with unhandled edge cases or missing error handling.
For minor/suggestion-level issues only, you may still Approve with notes."""


class ReviewerAgent(BaseAgent):
    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)

    async def run(self, plan: PlannerOutput, code: CoderOutput) -> ReviewerOutput:
        user_content = _format_input(plan, code)
        return await self._call_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=ReviewerOutput,
        )


def _format_input(plan: PlannerOutput, code: CoderOutput) -> str:
    return f"""=== ENGINEERING PLAN ===
{plan.model_dump_json(indent=2)}

=== PROPOSED CODE CHANGES ===
{code.model_dump_json(indent=2)}

Review the code against the plan and produce your review output."""
