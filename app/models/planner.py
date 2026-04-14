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



class PlannerOutput(BaseModel):
    developer_notes: DeveloperNotes
