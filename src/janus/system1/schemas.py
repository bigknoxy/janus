"""Laya question schemas — what the gate asks, and how answers map back to
System1Decision. Kept declarative so the engine file stays thin (SRP).
"""

from janus.core.types import IntentType

# Intent classification: a single low-cardinality `choice` question.
INTENT_QUESTION_KEY = "intent"

# Verb-led criteria phrasing — empirically the sharpest separation on the
# laya typed-decisions checkpoint (probed 2026-09-24, /tmp/qtest3 runs).
INTENT_CRITERIA = {
    IntentType.CODE_MODIFICATION.value: (
        "the user wants files changed: fix, add, refactor, implement, update"
    ),
    IntentType.EXPLANATION.value: (
        "the user wants understanding only: explain, describe, what does, how does, review"
    ),
    IntentType.DIRECT_ACTION.value: (
        "the user wants a command executed: run, deploy, git commit, install"
    ),
    IntentType.UNCLEAR_ESCALATE.value: (
        "the request cannot be safely routed to any other category"
    ),
}

# The typed-decisions subfolder checkpoint is tuned for exactly this
# four-workflow decision shape; base checkpoints route identically but
# softer (probed live on the laptop).
LAYA_MODEL = "typed-decisions"


def intent_question() -> dict:
    return {
        "type": "choice",
        "instructions": "What kind of request is this from a coding assistant's perspective?",
        "criteria": INTENT_CRITERIA,
    }


def file_relevance_question(path: str, file_symbols_summary: str) -> dict:
    """One noul question per candidate file — batched, so high file counts
    stay a single forward pass and never hit choice-cardinality limits."""
    return {
        "type": "noul",
        "instructions": (
            f"Does fulfilling the request likely require editing the file '{path}'?"
            + (f" It contains: {file_symbols_summary}." if file_symbols_summary else "")
        ),
    }
