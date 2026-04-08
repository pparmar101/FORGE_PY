from typing import Literal

from pydantic import BaseModel


class FileChange(BaseModel):
    file_path: str
    operation: Literal["create", "modify", "delete"]
    content: str | None = None  # full file content after change
    diff_summary: str


class UnitTest(BaseModel):
    file_path: str
    test_content: str  # full test file content


class CommitRecord(BaseModel):
    message: str  # format: type(JIRA-ID): message
    files: list[str]  # file paths included in this commit


class CoderOutput(BaseModel):
    code_changes: list[FileChange]
    tests: list[UnitTest]
    commits: list[CommitRecord]
    implementation_notes: str
