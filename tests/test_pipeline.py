"""End-to-end: orchestrator wiring all tiers with scripted engine fakes,
against a real temp project with a real failing test. Includes the spec'd
fixture: identify bug -> slice -> patch -> verify green; and the failure
branch: restore-parity rollback."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from janus.core.config import JanusSettings
from janus.core.orchestrator import PipelineOrchestrator, RunStatus
from janus.system1.mock_engine import MockDecisionEngine
from janus.system2.client import LocalGenerativeEngine
from janus.verification.runner import VerificationRunner

BUGGY = '''def calculate_tax(amount, rate=0.2):
    total = amount * rate
    return total
'''

FIXED = '''def calculate_tax(amount, rate=0.2):
    total = amount * (1 + rate)
    return total
'''

TEST_FILE = '''from calc import calculate_tax


def test_tax_adds_rate():
    assert calculate_tax(100, 0.2) == 120
'''

REPO_SUMMARY = "calc.py def calculate_tax(amount, rate)\ntest_calc.py"


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "calc.py").write_text(BUGGY)
    (tmp_path / "test_calc.py").write_text(TEST_FILE)
    return tmp_path


def s2_transport_returning(text: str):
    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {"choices": [{"message": {"content": text}}]}

    return transport


GOOD_PATCH = (
    "file: calc.py\n<<<<<<< SEARCH\n"
    "    total = amount * rate\n=======\n"
    "    total = amount * (1 + rate)\n>>>>>>> REPLACE"
)

BAD_PATCH = (
    "file: calc.py\n<<<<<<< SEARCH\n"
    "    total = amount * rate\n=======\n"
    "    total = amount  # broken\n>>>>>>> REPLACE"
)


def make_orchestrator(transport, settings: JanusSettings | None = None):
    settings = settings or JanusSettings(
        verify_command=f"{sys.executable} -m pytest -q test_calc.py"
    )
    return PipelineOrchestrator(
        s1=MockDecisionEngine(settings=settings),
        s2=LocalGenerativeEngine(settings=settings, transport=transport),
        runner=VerificationRunner(settings),
        settings=settings,
    )


class TestBranches:
    def test_explanation_spends_no_generation(self, project: Path):
        def boom(u, p, t):
            raise AssertionError("S2 must not be called for explanations")

        report = make_orchestrator(boom).run(
            "explain calculate_tax in calc.py", str(project), REPO_SUMMARY
        )
        assert report.status == RunStatus.READ_ONLY

    def test_low_confidence_escalates(self, project: Path):
        settings = JanusSettings(confidence_threshold=0.95)
        report = make_orchestrator(s2_transport_returning(GOOD_PATCH), settings).run(
            "fix calc.py", str(project), REPO_SUMMARY
        )
        assert report.status == RunStatus.ESCALATE


class TestE2EFixture:
    def test_bug_identified_patched_verified(self, project: Path):
        report = make_orchestrator(s2_transport_returning(GOOD_PATCH)).run(
            "fix calculate_tax in calc.py", str(project), REPO_SUMMARY
        )
        assert report.status == RunStatus.PATCHED_VERIFIED
        assert report.verification is not None and report.verification.passed
        assert (project / "calc.py").read_text() == FIXED

    def test_failed_patch_restores_files_byte_for_byte(self, project: Path):
        """S2 emits a patch that applies but fails tests; repair attempt also
        fails; originals must be restored with parity."""
        report = make_orchestrator(s2_transport_returning(BAD_PATCH)).run(
            "fix calculate_tax in calc.py", str(project), REPO_SUMMARY
        )
        assert report.status == RunStatus.FAILED_ROLLED_BACK
        assert (project / "calc.py").read_text() == BUGGY
        assert report.repair_note is not None and "Fix:" in report.repair_note

    def test_repair_loop_converges(self, project: Path):
        """First response garbage, second (with repair note) correct."""
        calls: list[dict[str, Any]] = []

        def two_stage(url: str, payload: dict[str, Any], t: float) -> dict[str, Any]:
            calls.append(payload)
            content = "no patches here" if len(calls) == 1 else GOOD_PATCH
            return {"choices": [{"message": {"content": content}}]}

        report = make_orchestrator(two_stage).run(
            "fix calculate_tax in calc.py", str(project), REPO_SUMMARY
        )
        assert report.status == RunStatus.PATCHED_VERIFIED
        assert len(calls) == 2
        second_user = calls[1]["messages"][1]["content"]
        assert "PREVIOUS ATTEMPT FAILED" in second_user

    def test_run_forced_matches_old_private_path(self, project: Path):
        """ISC-6: the public escalation-override API executes the same
        modification pipeline as the internal path."""
        from janus.core.types import IntentType, System1Decision

        orch = make_orchestrator(s2_transport_returning(GOOD_PATCH))
        forced = System1Decision(
            intent=IntentType.CODE_MODIFICATION,
            confidence=1.0,
            target_files=["calc.py"],
            micro_instruction="fix calculate_tax",
            requires_s2=True,
        )
        report = orch.run_forced(forced, str(project))
        assert report.status == RunStatus.PATCHED_VERIFIED
        assert (project / "calc.py").read_text() == FIXED

    def test_run_report_is_json_serializable(self, project: Path):
        report = make_orchestrator(s2_transport_returning(GOOD_PATCH)).run(
            "fix calculate_tax in calc.py", str(project), REPO_SUMMARY
        )
        json.loads(report.model_dump_json())
