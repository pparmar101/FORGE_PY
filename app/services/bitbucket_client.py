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

        # Build list of auth methods to try in order
        self._auth_options: list[tuple[str, str]] = []
        if settings.bitbucket_access_token:
            self._auth_options.append(("x-token-auth", settings.bitbucket_access_token))
            self._auth_options.append((settings.bitbucket_username, settings.bitbucket_access_token))
        if settings.bitbucket_app_password:
            self._auth_options.append((settings.bitbucket_username, settings.bitbucket_app_password))

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
            last_status = None
            for auth in self._auth_options:
                response = await client.post(
                    f"{self._base}/pullrequests",
                    json=payload,
                    auth=auth,
                    timeout=30,
                )
                last_status = response.status_code
                if response.status_code != 401:
                    break

            if response.status_code == 401:
                raise ValueError(
                    f"Bitbucket auth failed (401) with all credential options. "
                    f"Please create a Bitbucket App Password at "
                    f"https://bitbucket.org/account/settings/app-passwords "
                    f"and set BITBUCKET_APP_PASSWORD in .env"
                )
            response.raise_for_status()
            data = response.json()

        return data["links"]["html"]["href"]
