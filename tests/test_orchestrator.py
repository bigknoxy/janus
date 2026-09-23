"""System 2 client tests + prompt assembly contract (orchestration branch
tests land with the orchestrator in Step 6)."""

from typing import Any

import pytest

from janus.core.config import JanusSettings
from janus.system2.base import GenerativeEngineProtocol
from janus.system2.client import GenerationError, LocalGenerativeEngine
from janus.system2.prompt_templates import build_user_prompt


def good_transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": (
                        "file: app/calc.py\n<<<<<<< SEARCH\nx\n=======\ny\n"
                        ">>>>>>> REPLACE"
                    )
                }
            }
        ]
    }


class TestClient:
    def test_protocol_conformance(self):
        assert isinstance(LocalGenerativeEngine(), GenerativeEngineProtocol)

    def test_happy_path_extracts_content(self):
        engine = LocalGenerativeEngine(transport=good_transport)
        out = engine.generate_patch("do the thing")
        assert "<<<<<<< SEARCH" in out

    def test_payload_shape(self):
        captured: dict[str, Any] = {}

        def spy(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
            captured.update(payload)
            return good_transport(url, payload, timeout)

        s = JanusSettings(s2_model="qwen3-4b", s2_temperature=0.0)
        LocalGenerativeEngine(settings=s, transport=spy).generate_patch("hi")
        assert captured["model"] == "qwen3-4b"
        assert captured["temperature"] == 0.0
        assert captured["stream"] is False
        assert captured["messages"][0]["role"] == "system"

    def test_malformed_payload_raises_generation_error(self):
        engine = LocalGenerativeEngine(transport=lambda u, p, t: {"choices": []})
        with pytest.raises(GenerationError, match="malformed"):
            engine.generate_patch("hi")

    def test_empty_content_raises(self):
        engine = LocalGenerativeEngine(
            transport=lambda u, p, t: {"choices": [{"message": {"content": "  "}}]}
        )
        with pytest.raises(GenerationError, match="empty"):
            engine.generate_patch("hi")

    def test_transport_exception_propagates_as_generation_error(self):
        def boom(u: str, p: dict[str, Any], t: float) -> dict[str, Any]:
            raise GenerationError("endpoint error: connection refused")

        engine = LocalGenerativeEngine(transport=boom)
        with pytest.raises(GenerationError, match="connection refused"):
            engine.generate_patch("hi")


class TestPromptAssembly:
    def test_only_slices_and_instruction(self):
        prompt = build_user_prompt("fix the bug", {"app/calc.py": "def f():\n    pass"})
        assert "Task: fix the bug" in prompt
        assert "file: app/calc.py" in prompt
        assert "def f():" in prompt

    def test_empty_slices_rejected(self):
        with pytest.raises(ValueError, match="zero context"):
            build_user_prompt("fix", {})
