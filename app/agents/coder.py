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
- Commit messages MUST use the format: type(TICKET-ID): short description
  where TICKET-ID is the exact Jira ticket ID provided in the input (e.g. HACPM-162535).
  Types: feat, fix, refactor, test, chore.
  Example: feat(HACPM-162535): add unpublish endpoint for alternate hierarchy
- For each FileChange, provide the FULL file content after the change (not just a diff).
- For deleted files, set content to null.

CRITICAL — ADDITIVE CHANGES ONLY — Never modify existing functionality:
- Your role is to ADD new code, not change existing behaviour.
- You MUST preserve ALL existing methods, properties, fields, constructors, using statements,
  attributes, and comments exactly as they appear in the repo context.
- NEVER alter the body of an existing method — not even to "clean it up" or "fix a typo".
- NEVER rename, reorder, or remove existing parameters, return types, or access modifiers.
- NEVER change existing business logic, conditional branches, or return values.
- ONLY add: new methods, new properties, new classes, new endpoints, new enum values,
  new interface members, or new using statements needed for new code.
- If the file shown in repo context appears incomplete (truncated), reproduce everything
  up to the truncation point character-for-character, then append your additions after it.
- If you are unsure whether a line should change → DO NOT change it.

CRITICAL — Never modify project/solution files:
- Do NOT include .csproj, .vbproj, .sln, .fsproj, or any other project/solution files in code_changes.
- Do NOT modify package.json, tsconfig.json, webpack.config.js, or any build configuration files
  unless the plan explicitly requires it.
- Test files (.cs test classes) are allowed but must NOT be accompanied by .csproj modifications.

CRITICAL — Reuse existing DTOs — never invent new request/response models:
- Before creating any new class (request DTO, response model, view model), search the repo
  context and RAG snippets for an existing class that already has the required fields.
- If an existing DTO covers the needed fields, use it directly as the endpoint parameter —
  do NOT wrap it in a new class.
  Example: if ConsolAlternateHierarchyTaskData has GroupId, TimeId, HierarchyId — use it
  as `public IHttpActionResult MyEndpoint(ConsolAlternateHierarchyTaskData req)` directly.
- Only create a new DTO if no existing class has the required fields AND the plan
  explicitly names a new class to create.
- A new DTO that duplicates an existing one is a compilation warning and a maintenance burden.

CRITICAL — Complete the full call chain — never leave dangling references:
- If you add a method call in a controller (e.g. `_service.UnpublishAlternateHierarchy(req)`),
  you MUST also implement that method in the service class AND in the service interface.
- If you add a method to an interface, you MUST add the matching implementation in the concrete class.
- If you add a method to a service, you MUST add the matching signature to its interface.
- Before finishing, mentally trace every new method call you wrote and confirm the callee exists
  in your output. If it does not exist in the repo context, you must create it.
- "The method will be implemented later" is NOT acceptable — implement it now.
- Check each layer: Controller → Service Interface → Service Implementation → Repository (if applicable).

CRITICAL — Scope enforcement:
- Only change files listed in the engineering plan's impacted_files.
- If the plan lists 3 files, produce changes for at most those 3 files — no bonus files.
- Do NOT touch infrastructure, ADC, gateway, or SQL files unless they appear in impacted_files.

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
        rag_context: str = "",
        ticket_id: str = "",
    ) -> CoderOutput:
        user_content = _format_input(plan, repo_context, feedback, iteration, rag_context, ticket_id)
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
    rag_context: str = "",
    ticket_id: str = "",
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

    rag_section = ""
    if rag_context:
        rag_section = f"""
=== RETRIEVED CODE CONTEXT (RAG) ===
The following snippets from the codebase are semantically relevant to this ticket.
Use them to understand existing patterns, conventions, and related logic:

{rag_context}
=== END RETRIEVED CODE CONTEXT ===

"""

    ticket_line = f"Jira Ticket ID: {ticket_id}\n" if ticket_id else ""

    return f"""{feedback_section}{ticket_line}=== ENGINEERING PLAN ===
{plan.model_dump_json(indent=2)}

=== REPOSITORY CONTEXT (Impacted Files) ===
{repo_context if repo_context else "(No repo context available — this may be a new repository)"}

{rag_section}Implement the code changes described in the plan. Apply reviewer feedback if provided.
IMPORTANT: Every commit message MUST include the ticket ID '{ticket_id}' in the format: type({ticket_id}): description"""
