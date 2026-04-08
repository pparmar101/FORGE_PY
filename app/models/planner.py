from typing import Literal

from pydantic import BaseModel


class ImpactedFile(BaseModel):
    path: str
    change_type: Literal["create", "modify", "delete"]
    reason: str


class DeveloperNotes(BaseModel):
    step_by_step_plan: list[str]
    impacted_files: list[ImpactedFile]
    api_changes: list[str]
    db_changes: list[str]
    edge_cases: list[str]
    assumptions: list[str]


class TestCase(BaseModel):
    description: str
    test_type: Literal["positive", "negative", "regression"]
    steps: list[str]
    expected_result: str


class QANotes(BaseModel):
    test_cases: list[TestCase]
    regression_areas: list[str]


class Task(BaseModel):
    order: int
    title: str
    description: str
    estimated_complexity: Literal["low", "medium", "high"]


class TaskBreakdown(BaseModel):
    tasks: list[Task]


class PlannerOutput(BaseModel):
    developer_notes: DeveloperNotes
    qa_notes: QANotes
    task_breakdown: TaskBreakdown
