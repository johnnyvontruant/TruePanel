"""Optional local inference providers for Project WINGMAN."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class WingmanProvider(Protocol):
    """Minimal provider contract used by the advisory service."""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LlamaCppProvider:
    """OpenAI-compatible llama.cpp adapter with a local-only default boundary."""

    endpoint: str = "http://127.0.0.1:8080/v1/chat/completions"
    model: str = "wingman-local"
    timeout_seconds: float = 30.0
    allow_remote: bool = False

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("WINGMAN endpoint must use HTTP or HTTPS")
        host = (parsed.hostname or "").lower()
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        if not self.allow_remote and host not in local_hosts:
            raise ValueError("WINGMAN remote inference is disabled")
        if self.timeout_seconds <= 0:
            raise ValueError("WINGMAN timeout must be positive")

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 900,
            "stream": False,
            "response_format": {
                "type": "json_object",
                "schema": response_schema,
            },
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            decoded = json.loads(response.read().decode("utf-8"))
        content = decoded["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise ValueError("WINGMAN provider returned non-text content")
        answer = json.loads(content)
        if not isinstance(answer, dict):
            raise ValueError("WINGMAN provider returned non-object JSON")
        return answer


__all__ = ["LlamaCppProvider", "WingmanProvider"]
