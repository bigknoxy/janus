"""Laya question schemas — what the gate asks, and how answers map back to
System1Decision. Kept declarative so the engine file stays thin (SRP).
"""

from janus.core.types import IntentType

# Intent classification: a single low-cardinality `choice` question.
INTENT_QUESTION_KEY = "intent"

INTENT_CRITERIA = {
    IntentType.DIRECT_ACTION.value: (
        "run a command, git operation, or other non-code-editing action"
    ),
    IntentType.CODE_MODIFICATION.value: (
        "write, fix, refactor, or otherwise change source code"
    ),
    IntentType.EXPLANATION.value: (
        "explain, read, review, or answer a question without changing code"
    ),
    IntentType.UNCLEAR_ESCALATE.value: (
        "ambiguous, underspecified, or too risky to route automatically"
    ),
}


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
