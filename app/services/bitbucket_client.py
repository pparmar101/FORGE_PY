from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.models.reviewer import PRDetails

if TYPE_CHECKING:
    from app.config import Settings


class BitbucketClient:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self._base = settings.bitbucket_api_base

        # Auth: prefer single Bearer token, fall back to Basic (username + app password)
        if settings.bitbucket_access_token:
            self._auth = None
            self._headers = {"Authorization": f"Bearer {settings.bitbucket_access_token}"}
        else:
            self._auth = (settings.bitbucket_username, settings.bitbucket_app_password)
            self._headers = {}

    async def create_pull_request(
        self,
        pr_details: PRDetails,
        source_branch: str,
        destination_branch: str,
    ) -> str:
        """Create a PR on Bitbucket Cloud. Returns the PR URL."""
        payload = {
            "title": pr_details.title,
            "description": pr_details.description,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": destination_branch}},
            "close_source_branch": True,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base}/pullrequests",
                json=payload,
                auth=self._auth,          # None when using Bearer token
                headers=self._headers,    # has Authorization header if Bearer token
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

        return data["links"]["html"]["href"]
