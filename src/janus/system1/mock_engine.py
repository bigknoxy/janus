"""Deterministic, dependency-free System 1 for tests and offline dev.

Confidence is derived from keyword evidence so threshold transitions are
directly testable without a model. Satisfies DecisionEngineProtocol.
"""

from janus.core.config import JanusSettings
from janus.core.types import IntentType, System1Decision
from janus.system1.base import enforce_confidence_gate
from janus.system1.laya_engine import _candidate_files


class MockDecisionEngine:
    def __init__(self, settings: JanusSettings | None = None, confidence: float = 0.9):
        self._settings = settings or JanusSettings()
        self._confidence = confidence

    def evaluate(self, user_prompt: str, repo_summary: str) -> System1Decision:
        lowered = user_prompt.lower()
        modify_words = ("fix", "change", "refactor", "add", "implement", "update", "rewrite")
        explain_words = ("explain", "what does", "how does", "why", "describe", "review")

        if any(w in lowered for w in modify_words):
            intent, conf = IntentType.CODE_MODIFICATION, self._confidence
        elif any(w in lowered for w in explain_words):
            intent, conf = IntentType.EXPLANATION, self._confidence
        else:
            intent, conf = IntentType.UNCLEAR_ESCALATE, 0.5

        target_files = [
            p for p in _candidate_files(repo_summary) if p.split("/")[-1] in lowered
        ]
        decision = System1Decision(
            intent=intent,
            confidence=conf,
            target_files=target_files,
            target_symbols=[],
            micro_instruction=" ".join(user_prompt.split()),
            requires_s2=intent == IntentType.CODE_MODIFICATION,
        )
        return enforce_confidence_gate(decision, self._settings.confidence_threshold)
