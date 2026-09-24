"""System 2 client: OpenAI-compatible chat endpoint (Ollama, llama-server,
vLLM, the laptop's proxy — anything speaking /v1/chat/completions).

Transport is constructor-injected (DIP): tests pass a stub callable, never
mock the network. Errors surface as GenerationError — the orchestrator
decides whether failure is retryable, not the client.
"""

from collections.abc import Callable
from typing import Any

import httpx

from janus.core.config import JanusSettings
from janus.system2.prompt_templates import system_prompt


class GenerationError(Exception):
    """The generative endpoint failed or returned an unusable payload."""


TransportFn = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _httpx_transport(url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    try:
        resp = httpx.post(url, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        raise GenerationError(f"endpoint error: {e}") from e
    except ValueError as e:
        raise GenerationError(f"endpoint returned non-JSON: {e}") from e


class LocalGenerativeEngine:
    """GenerativeEngineProtocol over any OpenAI-compatible local server."""

    def __init__(
        self,
        settings: JanusSettings | None = None,
        transport: TransportFn | None = None,
    ) -> None:
        self._settings = settings or JanusSettings()
        self._transport = transport or _httpx_transport

    def generate_patch(self, prompt: str) -> str:
        s = self._settings
        payload = {
            "model": s.s2_model,
            "temperature": s.s2_temperature,
            "max_tokens": s.s2_max_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": prompt},
            ],
        }
        data = self._transport(
            f"{s.s2_base_url.rstrip('/')}/chat/completions", payload, s.s2_timeout_s
        )
        content = _extract_content(data)
        if s.s2_log_raw:
            _append_raw_log(s.s2_log_raw, prompt, content)
        return content


def _append_raw_log(path: str, prompt: str, content: str) -> None:
    """Dev capture: every raw S2 reply is corpus for the falsifier suite."""
    import json
    from pathlib import Path

    try:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"prompt": prompt, "raw": content}) + "\n")
    except OSError:
        pass


def _extract_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise GenerationError(f"malformed chat completion payload: {e}") from e
    if not isinstance(content, str) or not content.strip():
        raise GenerationError("model returned empty content")
    return content
