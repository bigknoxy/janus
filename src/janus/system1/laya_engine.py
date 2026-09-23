"""Laya-backed System 1.

Laya is a non-autoregressive decision model: typed questions in, calibrated
answers out, one forward pass. It imports lazily — the 808MB checkpoint and
the `laya` package are only touched when this engine is actually constructed
(`pip install janus-code[laya]`).
"""

from typing import Any

from janus.core.config import JanusSettings
from janus.core.types import IntentType, System1Decision
from janus.system1.base import enforce_confidence_gate
from janus.system1.schemas import (
    INTENT_QUESTION_KEY,
    file_relevance_question,
    intent_question,
)


class LayaDecisionEngine:
    """DecisionEngineProtocol implementation over a local Laya Router."""

    def __init__(self, settings: JanusSettings | None = None) -> None:
        self._settings = settings or JanusSettings()
        try:
            from laya import Router
        except ImportError as e:  # surfaced at construction, not mid-run
            raise RuntimeError(
                "laya is not installed; run `pip install janus-code[laya]`"
            ) from e
        self._router = Router(
            preload=self._settings.s1_preload, device=self._settings.s1_device
        )

    def evaluate(self, user_prompt: str, repo_summary: str) -> System1Decision:
        state = {"request": user_prompt, "repository": repo_summary}

        questions: dict[str, dict] = {INTENT_QUESTION_KEY: intent_question()}
        # Candidate files = one noul question per repo_map line that looks
        # like a path, so file selection stays batchable and unbounded.
        candidates = _candidate_files(repo_summary)
        for path in candidates:
            questions[f"file:{path}"] = file_relevance_question(path, "")

        result: dict[str, Any] = self._router.predict(state, questions)
        answers = result.get("answers", {})

        intent_answer = answers.get(INTENT_QUESTION_KEY, {})
        try:
            intent = IntentType(intent_answer.get("choice", IntentType.UNCLEAR_ESCALATE))
        except ValueError:
            intent = IntentType.UNCLEAR_ESCALATE
        confidence = float(intent_answer.get("confidence", 0.0))
        confidence = min(max(confidence, 0.0), 1.0)

        target_files = [
            key[len("file:"):]
            for key, ans in answers.items()
            if key.startswith("file:") and ans.get("noul", 0.0) >= 0.5
        ]

        decision = System1Decision(
            intent=intent,
            confidence=confidence,
            target_files=target_files,
            target_symbols=[],  # symbol-level narrowing is orchestrator+pruner work
            micro_instruction=" ".join(user_prompt.split()),
            requires_s2=intent == IntentType.CODE_MODIFICATION,
        )
        return enforce_confidence_gate(decision, self._settings.confidence_threshold)


def _candidate_files(repo_summary: str) -> list[str]:
    """Extract path-like tokens from a repo_map summary (one per line)."""
    paths = []
    for line in repo_summary.splitlines():
        token = line.strip().split(" ", 1)[0]
        if "/" in token or "." in token:
            paths.append(token)
    return paths[:64]  # question budget guard


