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
    decision: System1Decision, threshold: float, margin_floor: float = 0.20
) -> System1Decision:
    """Single home for the escalation rule (DRY).

    When the engine reports a margin (top1 - top2 probability gap), the
    margin governs: diffuse/ambiguous routing escalates, confident routing
    proceeds. Engines without margins (mock, legacy) fall back to the
    absolute-confidence threshold. Engines that deliberately escalate are
    always respected.
    """
    if decision.intent == IntentType.UNCLEAR_ESCALATE:
        return decision  # engine deliberately escalated; respect it
    if decision.margin is not None:
        ambiguous = decision.margin < margin_floor
    else:
        ambiguous = decision.confidence < threshold
    if not ambiguous:
        return decision
    return decision.model_copy(
        update={"intent": IntentType.UNCLEAR_ESCALATE, "requires_s2": False}
    )
