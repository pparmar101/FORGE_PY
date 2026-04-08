from typing import Literal

from pydantic import BaseModel


class Issue(BaseModel):
    severity: Literal["critical", "major", "minor", "suggestion"]
    file_path: str | None = None
    line_hint: str | None = None
    description: str
    suggested_fix: str


class Risk(BaseModel):
    category: Literal["performance", "security", "breaking_change", "reliability"]
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
