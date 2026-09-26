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
    decision: System1Decision,
    threshold: float,
    margin_floor: float = 0.04,
    modify_margin_floor: float = 0.04,
) -> System1Decision:
    """Single home for the escalation rule (DRY), asymmetric by risk:

    - File-writing intents need a wider margin (`modify_margin_floor`) —
      vague nouls cluster near 0.5 with margins around 0.10 on genuinely
      ambiguous prompts (dogfood 2026-09-25 caught one: "it's broken,
      make it work" routed to modify at margin 0.103).
    - Read-only / direct intents escalate only on near-ties.
    - Margin-less engines (mock) fall back to the absolute threshold.
    - Engines that deliberately escalate are always respected.
    """
    if decision.intent == IntentType.UNCLEAR_ESCALATE:
        return decision
    if decision.target_symbols:
        return decision  # literal anchors override probability hedges (day-5)
    if decision.margin is not None:
        floor = (
            modify_margin_floor
            if decision.intent == IntentType.CODE_MODIFICATION
            else margin_floor
        )
        ambiguous = decision.margin < floor
    else:
        ambiguous = decision.confidence < threshold
    if not ambiguous:
        return decision
    return decision.model_copy(
        update={"intent": IntentType.UNCLEAR_ESCALATE, "requires_s2": False}
    )
