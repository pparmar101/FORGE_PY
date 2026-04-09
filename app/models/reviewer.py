from typing import Literal  # noqa: F401 — used by Issue.severity and ReviewerOutput.final_decision

from pydantic import BaseModel


class Issue(BaseModel):
    severity: Literal["critical", "major", "minor", "suggestion"]
    file_path: str | None = None
    line_hint: str | None = None
    description: str
    suggested_fix: str


class Risk(BaseModel):
    category: str
    description: str
    mitigation: str


class PRDetails(BaseModel):
    title: str
    description: str
    testing_steps: list[str]
    risks: list[str]


class ReviewerOutput(BaseModel):
    review_feedback: list[Issue]
    risks: list[Risk]
    final_decision: Literal["Approve", "Request Changes"]
    pr_details: PRDetails
    summary: str
