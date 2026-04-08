from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, TypeVar

import anthropic
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def _call_structured(
        self,
        system_prompt: str,
        user_content: str,
        output_model: type[T],
    ) -> T:
        schema = json.dumps(output_model.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            "Respond with ONLY valid JSON that matches the following JSON Schema. "
            "Do not include markdown fences, explanation, or any text outside the JSON object.\n\n"
            f"Schema:\n{schema}"
        )

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=full_system,
            messages=[{"role": "user", "content": user_content}],
        )

        raw = response.content[0].text.strip()
        # Strip accidental markdown fences if Claude adds them despite instructions
        raw = _strip_json_fences(raw)
        return output_model.model_validate_json(raw)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    pattern = r"^```(?:json)?\s*\n?([\s\S]*?)\n?```$"
    match = re.match(pattern, text.strip())
    if match:
        return match.group(1).strip()
    return text
