from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import BaseAgent
from app.models.coder import CoderOutput
from app.models.planner import PlannerOutput

if TYPE_CHECKING:
    from app.config import Settings

SYSTEM_PROMPT = """You are a Senior Software Engineer implementing code based on a detailed engineering plan.

Rules:
- Follow existing code style and conventions shown in the repo context.
- Keep changes minimal and safe — do not modify files unrelated to the plan.
- Add proper error handling for all new code paths.
- Do not break existing functionality.
- Commit messages must use the format: type(JIRA-ID): short description
  (types: feat, fix, refactor, test, chore)
- For each FileChange, provide the FULL file content after the change (not just a diff).
- For deleted files, set content to null.

Your output will be applied directly to a git repository."""


class CoderAgent(BaseAgent):
    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)

    async def run(
        self,
        plan: PlannerOutput,
        repo_context: str,
        feedback: str | None = None,
        iteration: int = 1,
    ) -> CoderOutput:
        user_content = _format_input(plan, repo_context, feedback, iteration)
        return await self._call_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=CoderOutput,
        )


def _format_input(
    plan: PlannerOutput,
    repo_context: str,
    feedback: str | None,
    iteration: int,
) -> str:
    feedback_section = ""
    if feedback and iteration > 1:
        feedback_section = f"""
=== REVIEWER FEEDBACK (Iteration {iteration}) ===
The previous implementation was reviewed and changes were requested.
Please address ALL issues below in your revised implementation:

{feedback}
=== END REVIEWER FEEDBACK ===

"""

    return f"""{feedback_section}=== ENGINEERING PLAN ===
{plan.model_dump_json(indent=2)}

=== REPOSITORY CONTEXT ===
{repo_context if repo_context else "(No repo context available — this may be a new repository)"}

Implement the code changes described in the plan. Apply reviewer feedback if provided."""
