from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.models.jira import JiraTicket

if TYPE_CHECKING:
    from app.config import Settings


class JiraTicketNotFound(Exception):
    pass


class JiraClient:
    def __init__(self, settings: "Settings") -> None:
        self._base_url = settings.jira_url.rstrip("/")
        self._auth = (settings.jira_username, settings.jira_api_token)

    async def fetch_ticket(self, ticket_id: str) -> JiraTicket:
        url = f"{self._base_url}/rest/api/3/issue/{ticket_id}"
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                response = await client.get(
                    url,
                    auth=self._auth,
                    headers={"Accept": "application/json"},
                )
            if response.status_code == 404:
                raise JiraTicketNotFound(f"Ticket {ticket_id} not found (404)")
            response.raise_for_status()
            issue = response.json()
        except JiraTicketNotFound:
            raise
        except Exception as exc:
            raise JiraTicketNotFound(f"Ticket {ticket_id} not found: {exc}") from exc

        fields = issue.get("fields", {})

        assignee_field = fields.get("assignee")
        assignee = assignee_field.get("displayName") if assignee_field else None

        priority_field = fields.get("priority")
        priority = priority_field.get("name", "Medium") if priority_field else "Medium"

        issue_type_field = fields.get("issuetype")
        issue_type = issue_type_field.get("name", "Story") if issue_type_field else "Story"

        status_field = fields.get("status")
        status = status_field.get("name", "Open") if status_field else "Open"

        labels: list[str] = fields.get("labels", [])

        # Pull comment bodies (max 20) — body may be ADF dict or plain string
        comments_data = fields.get("comment", {}).get("comments", [])
        comments = []
        for c in comments_data[-20:]:
            body = c.get("body", "")
            if isinstance(body, dict):
                body = _extract_adf_text(body)
            if body:
                comments.append(body)

        description = fields.get("description") or ""
        # Jira Cloud returns ADF (Atlassian Document Format) objects; extract plain text if needed
        if isinstance(description, dict):
            description = _extract_adf_text(description)

        return JiraTicket(
            ticket_id=ticket_id,
            summary=fields.get("summary", ""),
            description=description,
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee=assignee,
            labels=labels,
            comments=comments,
        )


def _extract_adf_text(adf: dict) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    parts: list[str] = []

    def _walk(node: dict | list) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []):
                _walk(child)

    _walk(adf)
    return " ".join(parts).strip()
