import json
import re
from typing import Any

import httpx

from .config import Settings


class LLMProviderError(RuntimeError):
    """Raised when a configured LLM provider cannot return valid JSON."""


def redact_sensitive(value: str) -> str:
    patterns = (
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",
        r"(?i)((?:password|passwd|api[_-]?key|token|secret)\s*[=:]\s*)[^\s,;]+",
    )
    for pattern in patterns:
        value = re.sub(pattern, r"\1[REDACTED]", value)
    return value


def request_json(system_prompt: str, user_prompt: str, settings: Settings) -> dict[str, Any]:
    if settings.ai_provider != "openai_compatible":
        raise LLMProviderError(f"unsupported AI provider: {settings.ai_provider}")
    if not settings.ai_api_key:
        raise LLMProviderError("AI_API_KEY is required for the configured provider")

    url = f"{settings.ai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ai_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": redact_sensitive(user_prompt)},
        ],
    }
    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMProviderError("configured AI provider returned an invalid response") from exc
    if not isinstance(result, dict):
        raise LLMProviderError("configured AI provider did not return a JSON object")
    return result
