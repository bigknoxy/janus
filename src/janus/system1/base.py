"""System 1 contract: every decision engine speaks System1Decision.

The protocol is the seam (OCP/DIP): Laya, a mock, or an HTTP backend all
implement `evaluate` and are interchangeable without the orchestrator's
knowledge.
"""

from typing import Protocol, runtime_checkable

from janus.core.types import IntentType, System1Decision


@runtime_checkable
class DecisionEngineProtocol(Protocol):
    def evaluate(self, user_prompt: str, repo_summary: str) -> System1Decision:
        """Classify the request against a repo overview, with calibrated
        confidence. Never raises on valid strings; engines surface their
        uncertainty through the confidence field, not exceptions."""
        ...


def enforce_confidence_gate(
    decision: System1Decision, threshold: float
) -> System1Decision:
    """Single home for the escalation rule (DRY).

    Below the threshold the honest outcome is UNCLEAR_ESCALATE: the
    orchestrator asks the human before any generative inference is spent.
    """
    if decision.confidence >= threshold and decision.intent != IntentType.UNCLEAR_ESCALATE:
        return decision
    if decision.confidence >= threshold:
        return decision  # engine deliberately escalated; respect it
    return decision.model_copy(
        update={"intent": IntentType.UNCLEAR_ESCALATE, "requires_s2": False}
    )
