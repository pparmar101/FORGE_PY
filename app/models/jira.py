from pydantic import BaseModel


class JiraTicket(BaseModel):
    ticket_id: str
    summary: str
    description: str
    issue_type: str
    status: str
    priority: str
    assignee: str | None = None
    labels: list[str] = []
    comments: list[str] = []
