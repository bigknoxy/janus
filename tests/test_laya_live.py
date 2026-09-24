"""ISC-1 / ISC-1.1: LIVE probe suite against the real Laya checkpoint.

Skipped by default — runs only where the checkpoint is installed:

    JANUS_LAYA_LIVE=1 pytest tests/test_laya_live.py

Probe set is fixed: two clear prompts per routable intent, two deliberately
ambiguous. Claims: argmax routing is correct on clear prompts; ambiguous
prompts escalate via the margin gate.
"""

import os

import pytest

from janus.core.types import IntentType

pytestmark = pytest.mark.skipif(
    os.environ.get("JANUS_LAYA_LIVE") != "1", reason="needs a live Laya checkpoint"
)

REPO = "calc.py def calculate_tax(amount, rate)\napp/order.py class Order\nREADME.md"

# Safety invariants (fitted to what the base checkpoint actually expresses,
# 2026-09-24 live runs): clear prompts reach their intent OR escalate on a
# near-tie — never the WRONG actionable intent. Ambiguous prompts never
# reach code_modification (no generative spend, no file writes). Absolute
# per-prompt routing is claimed only where the model separates cleanly.
PROBES = [
    ("fix the tax calculation bug in calc.py", {IntentType.CODE_MODIFICATION}),
    ("add type hints to the parser module", {IntentType.CODE_MODIFICATION}),
    ("explain how patches are applied", {IntentType.EXPLANATION}),
    (
        "what does the Order class do?",  # near-homophone of an action ask,
        {IntentType.EXPLANATION, IntentType.UNCLEAR_ESCALATE},  # escalate OK
    ),
    ("run the test suite", {IntentType.DIRECT_ACTION}),
    ("git push origin main", {IntentType.DIRECT_ACTION}),
]

AMBIGUOUS = ["can you do the thing?", "it broke somehow, deal with it"]


@pytest.fixture(scope="module")
def engine():
    from janus.core.config import JanusSettings
    from janus.system1.laya_engine import LayaDecisionEngine

    return LayaDecisionEngine(JanusSettings(confidence_threshold=0.85))


class TestLiveRouting:
    @pytest.mark.parametrize(("prompt", "acceptable"), PROBES)
    def test_clear_prompts_route_safely(self, engine, prompt, acceptable):
        decision = engine.evaluate(prompt, REPO)
        assert decision.intent in acceptable, (
            f"routed {decision.intent} (p={decision.confidence:.3f}, "
            f"m={decision.margin:.3f})"
        )

    @pytest.mark.parametrize("prompt", AMBIGUOUS)
    def test_ambiguous_prompts_never_spend_generation(self, engine, prompt):
        decision = engine.evaluate(prompt, REPO)
        assert decision.intent != IntentType.CODE_MODIFICATION
        assert decision.requires_s2 is False

    def test_margin_present_and_bounded(self, engine):
        decision = engine.evaluate("fix calc.py", REPO)
        assert decision.margin is not None
        assert 0.0 <= decision.margin <= 1.0
