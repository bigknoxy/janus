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
        # doctrine day-5: margin floors guard near-ties only; anchors carry safety
        assert out.intent == IntentType.CODE_MODIFICATION and out.requires_s2

        near_tie = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.34, margin=0.02,
            micro_instruction="x", requires_s2=True,
        )
        assert (enforce_confidence_gate(near_tie, 0.85).intent
                == IntentType.UNCLEAR_ESCALATE)

        anchored = System1Decision(
            intent=IntentType.CODE_MODIFICATION, confidence=0.5, margin=0.0,
            target_symbols=["parse_rate"],  # literal anchor overrides hedges
            micro_instruction="x", requires_s2=True,
        )
        assert enforce_confidence_gate(anchored, 0.85).requires_s2 is True

        boundary = System1Decision(
            intent=IntentType.EXPLANATION, confidence=0.5, margin=0.20,
            micro_instruction="x", requires_s2=False,
        )
        assert (
            enforce_confidence_gate(boundary, 0.85).intent
            == IntentType.EXPLANATION
        )

    def test_deliberate_engine_escalation_is_respected(self):
        decision = System1Decision(
            intent=IntentType.UNCLEAR_ESCALATE,
            confidence=0.99,  # confident ABOUT the ambiguity
            micro_instruction="x",
            requires_s2=False,
        )
        assert enforce_confidence_gate(decision, 0.85).intent == IntentType.UNCLEAR_ESCALATE


class TestVagueTargetRule:
    """Day-2 dogfood rule: modify intent without any pinned path or
    confident file noul escalates deterministically (nouls can't separate
    vague from clear; prompt-structure can)."""

    def _engine_with(self, answers: dict):
        from janus.system1.laya_engine import LayaDecisionEngine

        class StubAgent:
            def predict(self, state, questions):
                return {"answers": answers}

        settings = JanusSettings(s1_backend="laya")
        engine = LayaDecisionEngine.__new__(LayaDecisionEngine)
        engine._settings = settings
        engine._agent = StubAgent()
        return engine

    def _modify_answers(self, margin_gap: float = 0.5) -> dict:
        return {
            "intent:code_modification": {"noul": 0.55},
            "intent:explanation": {"noul": 0.55 - margin_gap},
            "intent:direct_action": {"noul": 0.2},
            "intent:unclear_escalate": {"noul": 0.1},
            "file:mod.py": {"noul": 0.1},
        }

    def test_vague_unpinned_escalates(self):
        engine = self._engine_with(self._modify_answers())
        d = engine.evaluate("it's broken, make it work", "mod.py def add(a, b)")
        assert d.intent == IntentType.UNCLEAR_ESCALATE
        assert d.requires_s2 is False

    def test_pinned_prompt_still_routes(self):
        engine = self._engine_with(self._modify_answers())
        d = engine.evaluate("fix the bug in mod.py", "mod.py def add(a, b)")
        assert d.intent == IntentType.CODE_MODIFICATION

    def test_confident_file_noul_without_anchor_still_escalates(self):
        """Day-2 evidence: nouls spike on vague asks; anchors only."""
        answers = self._modify_answers()
        answers["file:mod.py"] = {"noul": 0.72}
        engine = self._engine_with(answers)
        d = engine.evaluate("make the thing work", "mod.py def add(a, b)")
        assert d.intent == IntentType.UNCLEAR_ESCALATE
        assert d.requires_s2 is False

    def test_symbol_anchor_pins_file_routes(self):
        engine = self._engine_with(self._modify_answers())
        d = engine.evaluate("fix add's subtraction", "mod.py def add(a, b)")
        assert d.intent == IntentType.CODE_MODIFICATION
        assert d.target_symbols == ["add"]
        assert d.target_files == ["mod.py"]


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
