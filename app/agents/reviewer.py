from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.base import BaseAgent
from app.models.coder import CoderOutput
from app.models.planner import PlannerOutput
from app.models.reviewer import ReviewerOutput

if TYPE_CHECKING:
    from app.config import Settings

SYSTEM_PROMPT = """You are a Staff Engineer performing a code review based on file diffs.

You will receive:
1. An engineering plan (developer notes and impacted files)
2. Proposed code changes as diff summaries — NOT full file content.
   Each change includes: file_path, operation (create/modify/delete), and a diff_summary
   describing what was added or changed in that file.

Your job:
- Base your entire review on the diff summaries provided. Do NOT ask for full file content —
  it is not available. Make your best assessment from the diffs.
- Verify the diffs match what the plan describes.
- Flag scope issues: files touched that are NOT in the plan's impacted_files.
- Flag obvious structural problems visible in the diffs:
  e.g. a controller diff adds a service call but no service file diff exists in the changes.
- Flag .csproj, .sln, or SQL file modifications as issues.
- Decide: "Approve" if the diffs look consistent with the plan, "Request Changes" only if
  there is a clear, specific problem visible in the diffs themselves.
- Write a complete PR title and description ready to be submitted.

CRITICAL — Additive-only enforcement (based on diffs):
- If a diff summary describes removal or replacement of existing logic → flag as CRITICAL.
- If a diff summary describes modification of an existing method body → flag as CRITICAL.
- Acceptable: diffs that describe adding new methods, new endpoints, new properties,
  new enum values, or new interface members.

CRITICAL — Broken call chain (visible from diffs):
- If a controller diff adds a call to e.g. `_service.UnpublishAlternateHierarchy()` but
  there is NO corresponding service or interface file in the change list → flag as CRITICAL.

For minor/suggestion-level issues, Approve with notes."""


class ReviewerAgent(BaseAgent):
    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)

    async def run(self, plan: PlannerOutput, code: CoderOutput) -> ReviewerOutput:
        user_content = _format_input(plan, code)
        return await self._call_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=user_content,
            output_model=ReviewerOutput,
            max_tokens_override=self.settings.openai_max_tokens_reviewer,
        )


def _format_input(plan: PlannerOutput, code: CoderOutput) -> str:
    # Strip full file content from code changes — the reviewer only needs the
    # diff summary, file path, and operation to assess correctness vs the plan.
    # Sending full file content (5–10k tokens per file) causes excessive latency.
    trimmed_changes = [
        {
            "file_path": fc.file_path,
            "operation": fc.operation,
            "diff_summary": fc.diff_summary,
        }
        for fc in code.code_changes
    ]
    trimmed_code = {
        "code_changes": trimmed_changes,
        "commits": [c.model_dump() for c in code.commits],
        "implementation_notes": code.implementation_notes,
        # tests: include file paths only, not full test content
        "tests": [{"file_path": t.file_path} for t in code.tests],
    }

    import json
    plan_for_reviewer = {"developer_notes": plan.developer_notes.model_dump()}
    return f"""=== ENGINEERING PLAN ===
{json.dumps(plan_for_reviewer, indent=2)}

=== PROPOSED CODE CHANGES (summaries — full content applied separately) ===
{json.dumps(trimmed_code, indent=2)}

Review the code changes against the plan and produce your review output."""
