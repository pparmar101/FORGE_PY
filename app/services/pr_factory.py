from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.models.reviewer import PRDetails

if TYPE_CHECKING:
    from app.config import Settings


class PRClient(Protocol):
    async def create_pull_request(
        self,
        pr_details: PRDetails,
        source_branch: str,
        destination_branch: str,
    ) -> str: ...


def get_pr_client(settings: "Settings") -> PRClient:
    """Return the appropriate PR client based on GIT_PLATFORM setting."""
    if settings.git_platform == "github":
        from app.services.github_client import GitHubClient
        return GitHubClient(settings)

    from app.services.bitbucket_client import BitbucketClient
    return BitbucketClient(settings)
