from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import AsyncGenerator

from app.agents.coder import CoderAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent
from app.config import Settings
from app.models.orchestrator import RunEvent, RunState, RunStatus
from app.models.reviewer import ReviewerOutput
from app.services.git_service import GitService
from app.services.jira_client import JiraClient
from app.services.pr_factory import get_pr_client


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

            # ── Step 2: Planner ───────────────────────────────────────────────
            await emit(_status_event(RunStatus.PLANNING, "planner"))
            state.status = RunStatus.PLANNING

            plan = await self.planner.run(ticket)
            state.planner_output = plan
            await emit(RunEvent(
                event_type="agent_complete",
                agent="planner",
                payload=plan.model_dump(),
            ))

            # ── Step 3: Clone/open repo + gather context ──────────────────────
            repo = self.git.clone_or_open()
            repo_context = self.git.get_repo_context(repo, plan.developer_notes.impacted_files)

            # ── Step 4: Coder → Reviewer feedback loop ────────────────────────
            code = None
            review = None
            feedback: str | None = None
            max_iterations = self.settings.max_coder_iterations

            for iteration in range(1, max_iterations + 2):
                state.iteration = iteration

                # Coder
                await emit(_status_event(RunStatus.CODING, "coder", iteration))
                state.status = RunStatus.CODING

                code = await self.coder.run(plan, repo_context, feedback, iteration)
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
            self.git.apply_code_changes(repo, code.code_changes)

            # Apply test files alongside code changes
            for test in code.tests:
                from app.models.coder import FileChange
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


def _branch_name(ticket_id: str) -> str:
    """Convert PROJ-123 → feature/proj-123."""
    slug = re.sub(r"[^a-zA-Z0-9-]", "-", ticket_id).lower().strip("-")
    return f"feature/{slug}"
