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

PROBES = [
    ("fix the tax calculation bug in calc.py", IntentType.CODE_MODIFICATION),
    ("add type hints to the parser module", IntentType.CODE_MODIFICATION),
    ("what does the Order class do?", IntentType.EXPLANATION),
    ("explain how patches are applied", IntentType.EXPLANATION),
    ("run the test suite", IntentType.DIRECT_ACTION),
    ("git push origin main", IntentType.DIRECT_ACTION),
]

AMBIGUOUS = ["can you do the thing?", "it broke somehow, deal with it"]


@pytest.fixture(scope="module")
def engine():
    from janus.core.config import JanusSettings
    from janus.system1.laya_engine import LayaDecisionEngine

    return LayaDecisionEngine(JanusSettings(confidence_threshold=0.85))


class TestLiveRouting:
    @pytest.mark.parametrize(("prompt", "expected"), PROBES)
    def test_clear_prompts_route_correctly(self, engine, prompt, expected):
        decision = engine.evaluate(prompt, REPO)
        assert decision.intent == expected, (
            f"routed {decision.intent} (p={decision.confidence:.3f}, "
            f"m={decision.margin:.3f})"
        )

    @pytest.mark.parametrize("prompt", AMBIGUOUS)
    def test_ambiguous_prompts_escalate(self, engine, prompt):
        decision = engine.evaluate(prompt, REPO)
        assert decision.intent == IntentType.UNCLEAR_ESCALATE
        assert decision.requires_s2 is False

    def test_margin_present_and_bounded(self, engine):
        decision = engine.evaluate("fix calc.py", REPO)
        assert decision.margin is not None
        assert 0.0 <= decision.margin <= 1.0
