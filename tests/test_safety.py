"""P0 audit findings, red-first:
  P0-1 path traversal: patches must never escape repo_root.
  P0-2 create-file patches: apply cleanly; rollback DELETES created files.
  P0-3 repair loop must not launder internal bugs into retry attempts.
"""

from pathlib import Path
from typing import Any

import pytest

from janus.core.config import JanusSettings
from janus.core.orchestrator import PipelineOrchestrator, RunStatus
from janus.core.types import IntentType, System1Decision
from janus.system1.mock_engine import MockDecisionEngine
from janus.system2.client import LocalGenerativeEngine
from janus.verification.runner import VerificationRunner


def s2_returning(text: str):
    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        return {"choices": [{"message": {"content": text}}]}

    return transport


def make_orchestrator(transport, project: Path, **overrides) -> PipelineOrchestrator:
    overrides.setdefault("verify_command", "true")  # controlled per test
    settings = JanusSettings(**overrides)
    return PipelineOrchestrator(
        s1=MockDecisionEngine(settings=settings),
        s2=LocalGenerativeEngine(settings=settings, transport=transport),
        runner=VerificationRunner(settings),
        settings=settings,
    )


MODIFY = dict(
    intent=IntentType.CODE_MODIFICATION,
    confidence=0.99,
    micro_instruction="x",
    requires_s2=True,
)


class TestPathTraversal:
    def test_traversal_patch_rejected_nothing_written(self, tmp_path: Path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        victim = tmp_path.parent / "victim_janus_pwn.txt"
        assert not victim.exists()
        evil = (
            "file: ../victim_janus_pwn.txt\n<<<<<<< SEARCH\n<<<<<<< SEARCH is a lie\n"
            "=======\npwned\n>>>>>>> REPLACE"
        )
        # Whole file needs a search match; try create-style content instead:
        evil = (
            "file: ../victim_janus_pwn.txt\n<<<<<<< SEARCH\nx = 1\n"
            "=======\npwned\n>>>>>>> REPLACE"
        )
        orch = make_orchestrator(s2_returning(evil), tmp_path)
        report = orch.run_forced(
            System1Decision(target_files=["mod.py"], **MODIFY), str(tmp_path)
        )
        assert report.status == RunStatus.FAILED_ROLLED_BACK
        assert not victim.exists(), "traversal patch escaped repo_root"


class TestCreateFile:
    def test_create_file_applies_and_verifies(self, tmp_path: Path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        create = (
            "file: new_mod.py\n<<<<<<< SEARCH\n\n=======\n"
            "def helper():\n    return 2\n>>>>>>> REPLACE"
        )
        orch = make_orchestrator(s2_returning(create), tmp_path)
        report = orch.run_forced(
            System1Decision(target_files=["mod.py"], **MODIFY), str(tmp_path)
        )
        assert report.status == RunStatus.PATCHED_VERIFIED
        assert (tmp_path / "new_mod.py").read_text() == "def helper():\n    return 2"

    def test_failed_run_deletes_created_file(self, tmp_path: Path):
        """Restore-parity for the create-file case: rollback = deletion."""
        (tmp_path / "mod.py").write_text("x = 1\n")
        (tmp_path / "test_mod.py").write_text("assert False\n")
        settings_orch = make_orchestrator(
            s2_returning(
                "file: new_mod.py\n<<<<<<< SEARCH\n\n=======\n"
                "y = 2\n>>>>>>> REPLACE"
            ),
            tmp_path,
            verify_command="false",
            max_repair_attempts=1,
        )
        report = settings_orch.run_forced(
            System1Decision(target_files=["mod.py"], **MODIFY), str(tmp_path)
        )
        assert report.status == RunStatus.FAILED_ROLLED_BACK
        assert not (tmp_path / "new_mod.py").exists(), "rollback must delete creations"
        assert (tmp_path / "mod.py").read_text() == "x = 1\n"


class TestRepairLoopTransparency:
    def test_internal_bugs_propagate_not_retry(self, tmp_path: Path):
        """P0-3: an internal TypeError in the loop must crash the run, not
        be disguised as a retryable generation failure."""
        (tmp_path / "mod.py").write_text("x = 1\n")

        def buggy(transport_out):
            def t(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
                return transport_out
            return t

        # Malformed payload (missing 'content') raises GenerationError: retryable → allowed.
        # A TypeError from OUR code must propagate. Simulate via MonkeyPatch:
        import janus.patcher.parser as parser_mod

        orch = make_orchestrator(
            s2_returning("<<<<<<< SEARCH\nx = 1\n=======\n\n>>>>>>> REPLACE"),
            tmp_path,
        )

        def explosion(text):
            raise TypeError("internal bug marker")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(parser_mod, "parse_patches", explosion)
        monkeypatch.setattr(
            "janus.core.orchestrator.parse_patches", explosion, raising=True
        )
        with pytest.raises(TypeError, match="internal bug marker"):
            orch.run_forced(
                System1Decision(target_files=["mod.py"], **MODIFY), str(tmp_path)
            )
        monkeypatch.undo()
