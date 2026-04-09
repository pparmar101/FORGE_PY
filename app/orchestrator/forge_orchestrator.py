from __future__ import annotations

import asyncio
import re
from datetime import datetime

from app.agents.coder import CoderAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent
from app.config import Settings
from app.models.orchestrator import RunEvent, RunState, RunStatus
from app.models.reviewer import ReviewerOutput
from app.services.git_service import GitService
from app.services.jira_client import JiraClient
from app.services.pr_factory import get_pr_client
from app.services.rag_service import RAGService


class ForgeOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jira = JiraClient(settings)
        self.git = GitService(settings)
        self.planner = PlannerAgent(settings)
        self.coder = CoderAgent(settings)
        self.reviewer = ReviewerAgent(settings)
        self.pr_client = get_pr_client(settings)

    async def run(
        self,
        ticket_id: str,
        state: RunState,
        queue: asyncio.Queue,
    ) -> None:
        """
        Main pipeline. Writes RunEvents into `queue` as they happen.
        Also updates `state` in-place so GET /runs/{id} reflects current progress.
        """

        async def emit(event: RunEvent) -> None:
            state.events.append(event)
            state.updated_at = datetime.utcnow()
            await queue.put(event)

        try:
            # ── Step 1: Fetch Jira ticket ─────────────────────────────────────
            await emit(_status_event(RunStatus.FETCHING_TICKET, "system"))
            state.status = RunStatus.FETCHING_TICKET

            ticket = await self.jira.fetch_ticket(ticket_id)
            state.ticket = ticket.model_dump()
            await emit(RunEvent(
                event_type="ticket_fetched",
                agent="system",
                payload=ticket.model_dump(),
            ))

            # ── Step 2: Clone/open repo first (planner needs repo structure) ───
            repo = self.git.clone_or_open()
            repo_structure = await asyncio.to_thread(self.git.get_repo_structure)

            # ── Step 3: RAG index + query for planner context ─────────────────
            planner_rag_context = ""
            rag = None
            if self.settings.rag_enabled:
                state.status = RunStatus.INDEXING
                await emit(RunEvent(event_type="status_change", agent="system",
                                    status=RunStatus.INDEXING,
                                    payload={"message": "Indexing repo for RAG (first run may take a moment)..."}))
                rag = RAGService(self.settings, self.git.workspace)
                indexed = await asyncio.to_thread(rag.index_repo)
                await emit(RunEvent(event_type="status_change", agent="system",
                                    status=RunStatus.INDEXING,
                                    payload={"message": f"RAG index ready — {indexed} chunks indexed."}))
                planner_rag_query = f"{ticket.summary}\n{ticket.description}"
                planner_rag_context = await asyncio.to_thread(rag.query, planner_rag_query)

            # ── Step 4: Planner (with repo structure + RAG context) ───────────
            await emit(_status_event(RunStatus.PLANNING, "planner"))
            state.status = RunStatus.PLANNING

            plan = await self.planner.run(ticket, repo_structure=repo_structure, rag_context=planner_rag_context)
            state.planner_output = plan
            await emit(RunEvent(
                event_type="agent_complete",
                agent="planner",
                payload=plan.model_dump(),
            ))

            # ── Step 5: Validate impacted file paths against real repo ─────────
            plan = _validate_impacted_files(plan, self.git.workspace)

            # ── Step 6: Gather file context + coder RAG query ─────────────────
            repo_context = self.git.get_repo_context(repo, plan.developer_notes.impacted_files)
            coder_rag_context = ""
            if rag is not None:
                coder_rag_query = f"{ticket.summary}\n{ticket.description}\n{plan.model_dump_json()}"
                coder_rag_context = await asyncio.to_thread(rag.query, coder_rag_query)

            # ── Step 7: Coder → Reviewer feedback loop ────────────────────────
            code = None
            review = None
            feedback: str | None = None
            max_iterations = self.settings.max_coder_iterations

            for iteration in range(1, max_iterations + 2):
                state.iteration = iteration

                # Coder
                await emit(_status_event(RunStatus.CODING, "coder", iteration))
                state.status = RunStatus.CODING

                code = await self.coder.run(plan, repo_context, feedback, iteration, rag_context=coder_rag_context, ticket_id=ticket_id)
                state.coder_output = code
                await emit(RunEvent(
                    event_type="agent_complete",
                    agent="coder",
                    payload=code.model_dump(),
                    iteration=iteration,
                ))

                # Reviewer
                await emit(_status_event(RunStatus.REVIEWING, "reviewer", iteration))
                state.status = RunStatus.REVIEWING

                review = await self.reviewer.run(plan, code)
                state.reviewer_output = review
                await emit(RunEvent(
                    event_type="agent_complete",
                    agent="reviewer",
                    payload=review.model_dump(),
                    iteration=iteration,
                ))

                if review.final_decision == "Approve":
                    break

                if iteration > max_iterations:
                    # Max iterations hit — proceed with best-effort code
                    break

                feedback = _format_feedback(review)

            # ── Step 5: Apply git changes ─────────────────────────────────────
            await emit(_status_event(RunStatus.APPLYING, "system"))
            state.status = RunStatus.APPLYING

            branch_name = _branch_name(ticket_id)
            state.branch_name = branch_name

            self.git.create_branch(repo, branch_name)
            self.git.apply_code_changes(repo, _filter_safe_changes(code.code_changes))

            # Apply test files alongside code changes (never apply project files)
            for test in code.tests:
                from app.models.coder import FileChange
                if not _is_project_file(test.file_path):
                    test_change = FileChange(
                        file_path=test.file_path,
                        operation="create",
                        content=test.test_content,
                        diff_summary=f"Add unit test: {test.file_path}",
                    )
                    self.git.apply_code_changes(repo, [test_change])

            self.git.commit_changes(repo, code.commits)
            self.git.push_branch(repo, branch_name)

            # ── Step 6: Create PR ─────────────────────────────────────────────
            await emit(_status_event(RunStatus.CREATING_PR, "system"))
            state.status = RunStatus.CREATING_PR

            pr_url = await self.pr_client.create_pull_request(
                pr_details=review.pr_details,
                source_branch=branch_name,
                destination_branch=self.settings.default_base_branch,
            )
            state.pr_url = pr_url
            state.status = RunStatus.COMPLETE

            await emit(RunEvent(
                event_type="run_complete",
                agent="system",
                status=RunStatus.COMPLETE,
                payload={
                    "pr_url": pr_url,
                    "branch_name": branch_name,
                    "final_decision": review.final_decision,
                    "iterations": state.iteration,
                },
            ))

        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = str(exc)
            await emit(RunEvent(
                event_type="error",
                agent="system",
                status=RunStatus.FAILED,
                payload={"error": str(exc)},
            ))
        finally:
            # Signal that the stream is done
            await queue.put(None)


def _status_event(
    status: RunStatus,
    agent: str,
    iteration: int = 1,
) -> RunEvent:
    return RunEvent(
        event_type="status_change",
        agent=agent,
        status=status,
        iteration=iteration,
    )


def _format_feedback(review: ReviewerOutput) -> str:
    """Summarise critical and major issues for the next Coder iteration."""
    issues = [
        i for i in review.review_feedback
        if i.severity in ("critical", "major")
    ]
    if not issues:
        # If only minor/suggestions caused "Request Changes", include all
        issues = review.review_feedback

    lines = []
    for issue in issues:
        location = f" in {issue.file_path}" if issue.file_path else ""
        lines.append(
            f"[{issue.severity.upper()}]{location}: {issue.description}\n"
            f"  Fix: {issue.suggested_fix}"
        )
    return "\n\n".join(lines)


def _validate_impacted_files(plan, workspace):
    """
    Remove impacted files whose paths don't exist in the repo
    AND aren't plausible new files (i.e. their parent directory doesn't exist).
    Prevents the coder from writing to hallucinated paths.
    """
    validated = []
    for f in plan.developer_notes.impacted_files:
        full_path = workspace / f.path
        parent_exists = full_path.parent.exists()
        file_exists = full_path.exists()
        # Keep if file exists OR if it's a plausible new file (parent dir exists)
        if file_exists or parent_exists:
            validated.append(f)
        # else: silently drop hallucinated path

    plan.developer_notes.impacted_files = validated
    return plan


_PROJECT_FILE_EXTENSIONS = {
    ".csproj", ".vbproj", ".fsproj", ".sln",
    ".vcxproj", ".njsproj", ".pyproj",
}


def _is_project_file(file_path: str) -> bool:
    """Return True if the file is a project/solution file that should never be modified."""
    from pathlib import Path
    return Path(file_path).suffix.lower() in _PROJECT_FILE_EXTENSIONS


def _filter_safe_changes(changes):
    """Strip out any .csproj/.sln changes the coder produced — these break builds when AI-modified."""
    safe = [c for c in changes if not _is_project_file(c.file_path)]
    skipped = [c.file_path for c in changes if _is_project_file(c.file_path)]
    if skipped:
        import logging
        logging.getLogger(__name__).warning(
            "FORGE blocked modification of project files: %s", skipped
        )
    return safe


def _branch_name(ticket_id: str) -> str:
    """Convert PROJ-123 → user/raswani/PROJ_123_YYYYMMDD_HHMM.
    Timestamp suffix ensures each FORGE run gets a unique branch,
    preserving previous runs rather than overwriting them.
    """
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    parts = ticket_id.upper().split("-", 1)
    if len(parts) == 2:
        return f"user/raswani/{parts[0]}_{parts[1]}_{ts}"
    return f"user/raswani/{ticket_id.upper()}_{ts}"
