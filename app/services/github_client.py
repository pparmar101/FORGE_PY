from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.models.reviewer import PRDetails

if TYPE_CHECKING:
    from app.config import Settings


class GitHubClient:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self._headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._base = (
            f"https://api.github.com/repos/{settings.github_owner}/{settings.github_repo}"
        )

    async def create_pull_request(
        self,
        pr_details: PRDetails,
        source_branch: str,
        destination_branch: str,
    ) -> str:
        """Create a PR on GitHub. Returns the PR URL."""
        payload = {
            "title": pr_details.title,
            "body": pr_details.description,
            "head": source_branch,
            "base": destination_branch,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base}/pulls",
                json=payload,
                headers=self._headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return data["html_url"]
