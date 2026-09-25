"""System 1 unit tests: threshold transitions, protocol conformance, and
mock routing — no model downloads required."""

import pytest

from janus.core.config import JanusSettings
from janus.core.types import IntentType, System1Decision
from janus.system1.base import (
    DecisionEngineProtocol,
    enforce_confidence_gate,
)
from janus.system1.mock_engine import MockDecisionEngine

REPO = "app/calc.py def calculate_tax(amount, rate)\napp/order.py class Order\nREADME.md"


class TestProtocolConformance:
    def test_mock_satisfies_protocol(self):
        assert isinstance(MockDecisionEngine(), DecisionEngineProtocol)


class TestConfidenceGate:
    @pytest.mark.parametrize(
        ("confidence", "expected"),
        [
            (0.849, IntentType.UNCLEAR_ESCALATE),
            (0.85, IntentType.CODE_MODIFICATION),
            (0.851, IntentType.CODE_MODIFICATION),
            (1.0, IntentType.CODE_MODIFICATION),
        ],
    )
    def test_threshold_boundary(self, confidence: float, expected: IntentType):
        settings = JanusSettings(confidence_threshold=0.85)
        engine = MockDecisionEngine(settings=settings, confidence=confidence)
        decision = engine.evaluate("fix calculate_tax in app/calc.py", REPO)
        assert decision.intent == expected
        assert decision.requires_s2 == (expected == IntentType.CODE_MODIFICATION)

    def test_gate_never_lowers_requires_s2_for_confident_modify(self):
        decision = System1Decision(
            intent=IntentType.CODE_MODIFICATION,
            confidence=0.99,
            micro_instruction="x",
            requires_s2=True,
        )
        assert enforce_confidence_gate(decision, 0.85).requires_s2 is True

    def test_margin_governs_when_present(self):
        """ISC-1.1: high-margin/low-prob routes; low-margin escalates."""
        confident = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.46, margin=0.31,
            micro_instruction="x", requires_s2=True,
        )
        out = enforce_confidence_gate(confident, 0.85)
        assert out.intent == IntentType.CODE_MODIFICATION and out.requires_s2

        diffuse = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.34, margin=0.08,
            micro_instruction="x", requires_s2=True,
        )
        out = enforce_confidence_gate(diffuse, 0.85)
        assert out.intent == IntentType.UNCLEAR_ESCALATE and not out.requires_s2

        boundary = System1Decision(
            intent=IntentType.EXPLANATION, confidence=0.5, margin=0.20,
            micro_instruction="x", requires_s2=False,
        )
        assert (
            enforce_confidence_gate(boundary, 0.85).intent
            == IntentType.EXPLANATION
        )

    def test_modify_needs_wider_margin(self):
        """Dogfood 2026-09-25: 'it's broken, make it work' reached
        code_modification at margin 0.103. Writing intents need 0.12."""
        vague = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.586, margin=0.103,
            micro_instruction="x", requires_s2=True,
        )
        assert enforce_confidence_gate(vague, 0.85).intent == IntentType.UNCLEAR_ESCALATE
        assert enforce_confidence_gate(vague, 0.85).requires_s2 is False

        clear = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.522, margin=0.148,
            micro_instruction="x", requires_s2=True,
        )
        assert enforce_confidence_gate(clear, 0.85).requires_s2 is True

        readonly = System1Decision(
            intent=IntentType.EXPLANATION, confidence=0.4, margin=0.08,
            micro_instruction="x", requires_s2=False,
        )
        # narrow floor (0.04) still routes cheap read-only intents
        assert enforce_confidence_gate(readonly, 0.85).intent == IntentType.EXPLANATION

    def test_deliberate_engine_escalation_is_respected(self):
        decision = System1Decision(
            intent=IntentType.UNCLEAR_ESCALATE,
            confidence=0.99,  # confident ABOUT the ambiguity
            micro_instruction="x",
            requires_s2=False,
        )
        assert enforce_confidence_gate(decision, 0.85).intent == IntentType.UNCLEAR_ESCALATE


class TestMockRouting:
    def test_modify_words_route_to_code_modification(self):
        d = MockDecisionEngine().evaluate("please fix the tax bug", REPO)
        assert d.intent == IntentType.CODE_MODIFICATION
        assert d.requires_s2 is True

    def test_explain_words_route_read_only(self):
        d = MockDecisionEngine().evaluate("explain how calculate_tax works", REPO)
        assert d.intent == IntentType.EXPLANATION
        assert d.requires_s2 is False

    def test_gibberish_escalates(self):
        d = MockDecisionEngine().evaluate("floop the whoozit", REPO)
        assert d.intent == IntentType.UNCLEAR_ESCALATE

    def test_target_files_matched_from_repo_summary(self):
        d = MockDecisionEngine().evaluate("fix calc.py", REPO)
        assert "app/calc.py" in d.target_files

    def test_micro_instruction_is_normalized(self):
        d = MockDecisionEngine().evaluate("fix   the\n  bug", REPO)
        assert d.micro_instruction == "fix the bug"
