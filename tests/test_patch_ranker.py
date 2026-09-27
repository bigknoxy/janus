"""Patch-candidate ranking (JB-3) — red-first.

Doctrine: deterministic verification is the ranker judge; Laya only
arbritrates WHICH candidate earns the verify cycle. When the ranker
has no signal (all nouls < 0.5), first-candidate-wins stays the law.
"""

import pytest

from janus.core.config import JanusSettings
from janus.core.orchestrator import PipelineOrchestrator
from janus.core.types import (
    IntentType,
    System1Decision,
    VerificationResult,
)
from janus.system1.patch_ranker import rank_by_scores


class _MultiStubS2:
    """Generates a fixed list of candidate outputs, one per call."""

    def __init__(self, outputs: list[str]):
        self._outputs = outputs

    def generate_patches(self, _prompt: str, n: int = 1) -> list[str]:
        return (self._outputs * n)[:n]

    def generate_patch(self, prompt: str, temperature: float | None = None) -> str:
        return self._outputs[0]


class _StaticRankerS1:
    """S1 double whose rank_patches returns a fixed ordering."""

    def __init__(self, order: list[int]):
        self._order = order

    def rank_patches(self, _instruction: str, candidates: list[str]) -> list[int]:
        return self._order

    def evaluate(self, _p, _s) -> System1Decision:
        return System1Decision(
            intent=IntentType.CODE_MODIFICATION,
            confidence=0.99,
            micro_instruction="fix add",
            target_files=["mod.py"],
            target_symbols=["add"],
            requires_s2=True,
        )


class _AlwaysFailRunner:
    def run(self, _root: str) -> VerificationResult:
        return VerificationResult(command="true", exit_code=0, passed=True, stdout="", stderr="")


GOOD = (
    "file: mod.py\n<<<<<<< SEARCH\ndef add(a, b):\n    return a - b\n=======\n"
    "def add(a, b):\n    return a + b\n>>>>>>> REPLACE"
)
BAD = "file: mod.py\n<<<<<<< SEARCH\nnope no match\n=======\nx\n>>>>>>> REPLACE"


def test_rank_by_scores_first_wins_when_no_signal():
    # all < 0.5 → identity order
    assert rank_by_scores([0.3, 0.45, 0.1]) == [0, 1, 2]


def test_rank_by_scores_prefers_highest_above_half():
    assert rank_by_scores([0.4, 0.7, 0.6]) == [1, 2, 0]


def test_rank_by_scores_never_drops_candidates():
    out = rank_by_scores([0.9, 0.8])
    assert sorted(out) == [0, 1]


def test_orchestrator_applies_ranked_champion(tmp_path):
    """A ranker that puts candidate 1 first must rescue a run whose
    unranked first candidate was world-logic noise."""
    (tmp_path / "mod.py").write_text("def add(a, b):\n    return a - b\n")
    s1 = _StaticRankerS1([1, 0])
    s2 = _MultiStubS2([BAD, GOOD])
    settings = JanusSettings(s1_rank_candidates=2, max_repair_attempts=0)
    orch = PipelineOrchestrator(s1, s2, runner=_AlwaysFailRunner(), settings=settings)  # type: ignore[arg-type]
    report = orch.run_modify(
        s1.evaluate("", ""), str(tmp_path)
    )
    from janus.core.orchestrator import RunStatus

    assert report.status == RunStatus.PATCHED_VERIFIED
    assert (tmp_path / "mod.py").read_text() == "def add(a, b):\n    return a + b\n"
    assert report.arbitration is not None
    assert report.arbitration["chosen"] == 1
    assert report.arbitration["candidates"] == 2


def test_ranker_off_by_default_preserves_old_path(tmp_path):
    (tmp_path / "mod.py").write_text("def add(a, b):\n    return a - b\n")
    s1 = _StaticRankerS1([0])
    s2 = _MultiStubS2([GOOD])
    settings = JanusSettings(max_repair_attempts=0)  # ranker OFF
    orch = PipelineOrchestrator(s1, s2, runner=_AlwaysFailRunner(), settings=settings)  # type: ignore[arg-type]
    report = orch.run_modify(s1.evaluate("", ""), str(tmp_path))
    assert report.arbitration is None


def test_ranker_falls_back_to_single_candidate_without_generate_patches(tmp_path):
    """Engines exposing only generate_patch (older protocol) must still
    work when ranking is on — one candidate, identity order."""

    class _OldS2(_MultiStubS2):
        def __getattribute__(self, name):  # hide the plural method
            if name == "generate_patches":
                raise AttributeError(name)
            return object.__getattribute__(self, name)

    (tmp_path / "mod.py").write_text("def add(a, b):\n    return a - b\n")
    s1 = _StaticRankerS1([0])
    settings = JanusSettings(s1_rank_candidates=3, max_repair_attempts=0)
    orch = PipelineOrchestrator(
        s1, _OldS2([GOOD]), runner=_AlwaysFailRunner(), settings=settings
    )  # type: ignore[arg-type]
    report = orch.run_modify(s1.evaluate("", ""), str(tmp_path))
    from janus.core.orchestrator import RunStatus

    assert report.status == RunStatus.PATCHED_VERIFIED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
