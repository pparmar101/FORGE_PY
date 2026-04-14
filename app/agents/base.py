from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, TypeVar

import openai
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class BaseAgent:
    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def _call_structured(
        self,
        system_prompt: str,
        user_content: str,
        output_model: type[T],
        max_tokens_override: int | None = None,
    ) -> T:
        schema = json.dumps(output_model.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            "Respond with ONLY valid JSON that matches the following JSON Schema. "
            "Do not include markdown fences, explanation, or any text outside the JSON object.\n\n"
            f"Schema:\n{schema}"
        )

        max_tokens = max_tokens_override if max_tokens_override else self.max_tokens
        response = await self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_content},
            ],
        )

        finish_reason = response.choices[0].finish_reason
        content = response.choices[0].message.content
        if not content:
            raise ValueError(
                f"Model returned empty response for {output_model.__name__}. "
                f"Finish reason: {finish_reason}"
            )
        if finish_reason == "length":
            raise ValueError(
                f"Model response truncated (hit token limit) for {output_model.__name__}. "
                f"Increase OPENAI_MAX_TOKENS (currently {self.max_tokens})."
            )
        raw = content.strip()
        # Strip accidental markdown fences if the model adds them despite instructions
        raw = _strip_json_fences(raw)
        return output_model.model_validate_json(raw)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    pattern = r"^```(?:json)?\s*\n?([\s\S]*?)\n?```$"
    match = re.match(pattern, text.strip())
    if match:
        return match.group(1).strip()
    return text
