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

    def _is_local_path(self) -> bool:
        """Return True if the target repo URL is a local filesystem path."""
        url = self.settings.target_repo_url
        return not url.startswith(("http://", "https://", "git@", "ssh://"))

    def clone_or_open(self) -> git.Repo:
        """Open local repo directly, or clone remote repo if not already present."""
        if self._is_local_path():
            # Local path — open repo, searching parent dirs for .git if needed
            return git.Repo(self.workspace, search_parent_directories=True)

        if (self.workspace / ".git").exists():
            repo = git.Repo(self.workspace)
            try:
                repo.git.execute(["git", "-c", "GIT_TERMINAL_PROMPT=0", "fetch", "origin"])
            except Exception:
                pass  # offline or credential issue — use local state
            return repo

        self.workspace.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.clone_from(self.settings.target_repo_url, self.workspace)
        return repo

    def create_branch(self, repo: git.Repo, branch_name: str) -> None:
        """Checkout base branch then create and switch to a new feature branch."""
        base = self.settings.default_base_branch
        repo.git.checkout(base)
        # Only pull if the repo is remote — skip for local repos to avoid
        # Windows Credential Manager popups on the HTTPS origin remote.
        if not self._is_local_path():
            try:
                repo.git.execute([
                    "git", "-c", "GIT_TERMINAL_PROMPT=0",
                    "pull", "origin", base,
                ])
            except Exception:
                pass  # no remote or offline — continue with local state
        # Delete local branch if it already exists from a previous run
        existing = [b.name for b in repo.branches]
        if branch_name in existing:
            repo.git.branch("-D", branch_name)
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
        """Push the feature branch to origin, injecting credentials when available.

        Uses git's http.extraHeader to pass a Base64-encoded Basic auth token,
        which avoids URL-parsing issues caused by special characters (e.g. '@')
        in Bitbucket usernames / email addresses.
        """
        import base64

        if self.settings.git_platform == "github" and self.settings.github_token:
            # GitHub: embed token in URL (no @ in username so safe)
            push_url = (
                f"https://x-token-auth:{self.settings.github_token}@github.com/"
                f"{self.settings.github_owner}/{self.settings.github_repo}.git"
            )
            repo.git.push(push_url, branch_name)
        elif self.settings.git_platform == "bitbucket" and self.settings.bitbucket_workspace:
            # Bitbucket: use SSH to avoid HTTPS credential prompts entirely.
            # SSH key ~/.ssh/id_ed25519_bitbucket must be registered on the Bitbucket account.
            ssh_url = (
                f"git@bitbucket.org:"
                f"{self.settings.bitbucket_workspace}/{self.settings.bitbucket_repo_slug}.git"
            )
            repo.git.push(ssh_url, branch_name)
        else:
            repo.git.push("origin", branch_name)

    def get_repo_structure(self, max_files: int = 300) -> str:
        """
        Walk the repo and return a compact file tree string for stack detection.
        Skips build artefacts and dependency directories.
        """
        skip_dirs = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "bin", "obj", "dist", "build", ".idea", ".vs", "packages",
            "TestResults", ".forge_rag",
        }
        lines: list[str] = []
        count = 0
        for root, dirs, files in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            rel_root = os.path.relpath(root, self.workspace)
            depth = rel_root.count(os.sep)
            indent = "  " * depth
            folder = os.path.basename(root)
            if rel_root != ".":
                lines.append(f"{indent}{folder}/")
            for fname in files:
                lines.append(f"{'  ' * (depth + 1)}{fname}")
                count += 1
                if count >= max_files:
                    lines.append("  ... (truncated)")
                    return "\n".join(lines)
        return "\n".join(lines)

    def get_planner_context(self, planner_paths: list) -> str:
        """
        Read all source files from the planner folders defined in FORGE_INDEX.md
        and return them as a concatenated string for the planner agent.
        Only reads files with indexable extensions — skips binaries and build artefacts.
        """
        from app.services.rag_service import INDEXABLE_EXTENSIONS, SKIP_DIRS
        import os

        parts: list[str] = []

        def _read_file(fpath: Path) -> None:
            if fpath.suffix.lower() not in INDEXABLE_EXTENSIONS:
                return
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if len(content) > 10000:
                    content = content[:10000] + "\n... [truncated] ..."
                try:
                    rel = fpath.relative_to(self.workspace)
                except ValueError:
                    rel = fpath
                parts.append(f"### {rel}\n```\n{content}\n```\n")
            except Exception:
                pass

        for entry in planner_paths:
            entry = Path(entry)
            if not entry.exists():
                continue
            if entry.is_file():
                # Individual file entry (e.g. HierarchyConstants.cs)
                _read_file(entry)
            else:
                # Folder entry — walk recursively
                for root, dirs, files in os.walk(entry):
                    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                    for fname in files:
                        _read_file(Path(root) / fname)

        return "\n".join(parts)

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
                # Truncate only very large files — 8000 was too small and caused
                # the coder to regenerate files with missing code (silent deletions).
                # 40000 chars (~10k tokens) is safe with a 32k token model budget.
                if len(content) > 40000:
                    content = content[:40000] + "\n... [truncated — file too large, only modify the section relevant to the plan] ..."
                parts.append(f"### {impacted.path}\n```\n{content}\n```\n")
            except Exception as exc:
                parts.append(f"### {impacted.path}\n(Could not read: {exc})\n")

        return "\n".join(parts) if parts else ""
