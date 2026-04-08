from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import git

from app.models.coder import FileChange
from app.models.planner import ImpactedFile

if TYPE_CHECKING:
    from app.config import Settings


class GitService:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self.workspace = Path(settings.target_repo_local_path)

    def clone_or_open(self) -> git.Repo:
        """Clone the target repo if not already present, otherwise open it."""
        if (self.workspace / ".git").exists():
            repo = git.Repo(self.workspace)
            # Fetch latest from origin
            repo.remotes.origin.fetch()
            return repo

        self.workspace.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.clone_from(
            self.settings.target_repo_url,
            self.workspace,
        )
        return repo

    def create_branch(self, repo: git.Repo, branch_name: str) -> None:
        """Checkout base branch then create and switch to a new feature branch."""
        base = self.settings.default_base_branch
        repo.git.checkout(base)
        repo.git.pull("origin", base)
        repo.git.checkout("-b", branch_name)

    def apply_code_changes(self, repo: git.Repo, changes: list[FileChange]) -> None:
        """Write file changes to disk."""
        for change in changes:
            target = self.workspace / change.file_path

            if change.operation == "delete":
                if target.exists():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                content = change.content or ""
                target.write_text(content, encoding="utf-8")

    def commit_changes(self, repo: git.Repo, commits: list) -> None:
        """Stage and commit changes atomically per commit record."""
        for commit_record in commits:
            files_to_stage = commit_record.files
            if not files_to_stage:
                continue

            # Stage only the files listed in this commit
            repo.index.add([
                str(self.workspace / f)
                for f in files_to_stage
                if (self.workspace / f).exists()
            ])
            # Also stage deletions
            for f in files_to_stage:
                path = self.workspace / f
                if not path.exists():
                    try:
                        repo.index.remove([str(path)], r=True)
                    except Exception:
                        pass

            repo.index.commit(commit_record.message)

    def push_branch(self, repo: git.Repo, branch_name: str) -> None:
        """Push the feature branch to origin."""
        repo.remotes.origin.push(branch_name)

    def get_repo_context(
        self, repo: git.Repo, impacted_files: list[ImpactedFile]
    ) -> str:
        """Read impacted files and return concatenated content for agent context."""
        parts: list[str] = []

        for impacted in impacted_files:
            path = self.workspace / impacted.path
            if not path.exists():
                parts.append(
                    f"### {impacted.path}\n"
                    f"(File does not exist yet — will be created)\n"
                )
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                # Truncate very large files to avoid blowing the context window
                if len(content) > 8000:
                    content = content[:8000] + "\n... [truncated] ..."
                parts.append(f"### {impacted.path}\n```\n{content}\n```\n")
            except Exception as exc:
                parts.append(f"### {impacted.path}\n(Could not read: {exc})\n")

        return "\n".join(parts) if parts else ""
