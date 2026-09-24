"""Laya question schemas — what the gate asks, and how answers map back to
System1Decision. Kept declarative so the engine file stays thin (SRP).
"""

from janus.core.types import IntentType

# Intent classification: a single low-cardinality `choice` question.
# Per-intent noul questions (batched — one forward pass). Probed live on
# the laptop (2026-09-24): nouls separate argmax intent cleanly on clear
# prompts where the single 4-way choice collapsed to near-ties.
INTENT_NOUL_QUESTIONS = {
    IntentType.CODE_MODIFICATION.value: (
        "Does the request ask to change the contents of source code files, "
        "e.g. fix, add, refactor, implement, annotate, or update code?"
    ),
    IntentType.EXPLANATION.value: (
        "Does the request only ask to read or understand code — explain, "
        "describe, or answer a question — with no file changes?"
    ),
    IntentType.DIRECT_ACTION.value: (
        "Does the request ask to execute or run a shell command, git "
        "operation, test suite, or deployment?"
    ),
    IntentType.UNCLEAR_ESCALATE.value: (
        "Is the request too vague or ambiguous to route to code change, "
        "explanation, or command execution?"
    ),
}


def intent_questions() -> dict[str, dict]:
    return {
        f"intent:{intent}": {"type": "noul", "instructions": text}
        for intent, text in INTENT_NOUL_QUESTIONS.items()
    }

# The typed-decisions subfolder checkpoint is tuned for exactly this
# decision-workflow shape; base checkpoints route identically but softer
# (probed live on the laptop).
LAYA_MODEL = "typed-decisions"

# Margin floor: fitted on the 8-prompt live probe suite (clear margins
# 0.045+, ambiguous-below). KNOWN to nearly overlap on hard prompts —
# re-fit as the harvested corpus grows (ISC-4).
DEFAULT_MARGIN_FLOOR = 0.04


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
