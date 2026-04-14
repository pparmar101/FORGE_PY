from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # OpenAI
    openai_api_key: str

    # Jira
    jira_url: str
    jira_username: str
    jira_api_token: str

    # Git Platform
    git_platform: Literal["bitbucket", "github"] = "bitbucket"

    # Bitbucket
    bitbucket_workspace: str = ""
    bitbucket_repo_slug: str = ""
    bitbucket_username: str = ""
    bitbucket_app_password: str = ""
    # Optional: single Bearer token (overrides username+app_password if set)
    bitbucket_access_token: str = ""

    # GitHub
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""

    # Git / Target Repo
    target_repo_url: str
    target_repo_local_path: str = "/tmp/forge_workspace"
    default_base_branch: str = "main"

    # FastAPI
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:8501"]

    # OpenAI Model
    openai_model: str = "gpt-4.5-preview"
    openai_max_tokens: int = 32768          # coder (needs full file output)
    openai_max_tokens_planner: int = 8192   # plan JSON only, no code
    openai_max_tokens_reviewer: int = 4096  # decision + notes only

    # Orchestrator
    max_coder_iterations: int = 0

    # RAG
    rag_enabled: bool = True
    rag_top_k: int = 8

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def bitbucket_api_base(self) -> str:
        return (
            f"https://api.bitbucket.org/2.0/repositories/"
            f"{self.bitbucket_workspace}/{self.bitbucket_repo_slug}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
