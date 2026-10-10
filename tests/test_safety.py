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


class TestOrchestratorBranches:
    def test_no_slices_escalates(self, tmp_path: Path):
        orch = make_orchestrator(s2_returning("no blocks"), tmp_path)
        report = orch.run_forced(
            System1Decision(target_files=["does_not_exist.py"], **MODIFY),
            str(tmp_path),
        )
        assert report.status == RunStatus.ESCALATE
        assert "no matching" in report.message

    def test_traversal_in_collect_slices_raises(self, tmp_path: Path):
        orch = make_orchestrator(s2_returning("no blocks"), tmp_path)
        with pytest.raises(Exception, match="escapes"):
            orch.run_forced(
                System1Decision(target_files=["../../etc/passwd"], **MODIFY),
                str(tmp_path),
            )

    def test_ambiguous_pathless_patch_rejected(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("x = 1\n")
        raw = "<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE"
        orch = make_orchestrator(s2_returning(raw), tmp_path)
        report = orch.run_forced(
            System1Decision(target_files=["a.py", "b.py"], **MODIFY), str(tmp_path)
        )
        assert report.status == RunStatus.FAILED_ROLLED_BACK
        assert (tmp_path / "a.py").read_text() == "x = 1\n"
        assert (tmp_path / "b.py").read_text() == "x = 1\n"

    def test_read_only_and_direct_statuses(self, tmp_path: Path):
        orch = make_orchestrator(s2_returning(""), tmp_path)
        from janus.core.types import IntentType as IT

        ro = orch.run_forced(
            System1Decision(intent=IT.EXPLANATION, confidence=0.9,
                            micro_instruction="x", requires_s2=False),
            str(tmp_path),
        )
        # run_forced always modifies; READ_ONLY flows through run() instead:
        assert ro.status in (RunStatus.ESCALATE, RunStatus.FAILED_ROLLED_BACK)
        report = orch.run("explain calc", str(tmp_path), "calc.py def x")
        assert report.status == RunStatus.READ_ONLY


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

    def test_bare_pytest_routed_through_janus_interpreter(self, tmp_path: Path):
        """Real-use finding (2026-10-02): a bare `pytest` resolves against the
        inherited PATH and misses a venv-installed janus (the venv's bin/ is
        not on PATH unless the caller activated it). The runner must route it
        through the interpreter janus itself runs under."""
        runner = VerificationRunner(JanusSettings(verify_command="pytest --version"))
        result = runner.run(cwd=str(tmp_path))
        assert result.passed, f"runner lost pytest: {result.stderr}"


class TestBigFileSlicing:
    def test_big_file_sliced_by_ranked_symbol(self, tmp_path: Path):
        """Dogfood 2026-10-08: a big file (>12K chars) with no verbatim
        symbol got ZERO slices and ESCALATE'd — the whole-file rule only
        covered <12K. The big-file path now extracts top-level symbols and
        lets the S1 arbitrate by noul; the top-ranked symbol's slice is
        the S2's context (mock has no ranker → identity order → first
        candidate wins, same doctrine as patch ranking)."""
        body = "    x = 1\n" * 900  # 900 lines * 10 chars = 9K per function
        (tmp_path / "mod.py").write_text(
            f"def broken():\n{body}    return 1\n\n\ndef filler():\n{body}    return 2\n"
        )
        assert (tmp_path / "mod.py").stat().st_size > 12_000
        good = (
            "file: mod.py\n<<<<<<< SEARCH\n    return 1\n"
            "=======\n    return 2\n>>>>>>> REPLACE"
        )
        settings = JanusSettings(verify_command="true")
        orch = PipelineOrchestrator(
            s1=MockDecisionEngine(settings=settings),
            s2=LocalGenerativeEngine(settings=settings, transport=s2_returning(good)),
            runner=VerificationRunner(settings),
            settings=settings,
        )
        report = orch.run("fix mod.py: it returns one item too few", str(tmp_path), "mod.py")
        assert report.status == RunStatus.PATCHED_VERIFIED, report.message

    def test_big_file_without_symbols_still_slices(self, tmp_path: Path):
        """A big file whose top-level symbols can't be extracted (malformed
        source) falls back to the first extractable symbol or escalates
        honestly — never a silent empty slice from the size rule alone."""
        (tmp_path / "mod.py").write_text("def broken():\n" + "    x = 1\n" * 2000)
        settings = JanusSettings(verify_command="true")
        orch = PipelineOrchestrator(
            s1=MockDecisionEngine(settings=settings),
            s2=LocalGenerativeEngine(settings=settings, transport=s2_returning("no patch")),
            runner=VerificationRunner(settings),
            settings=settings,
        )
        # Slices exist (extractable symbols) → the S2's failed patch →
        # FAILED_ROLLED_BACK, NOT the slicer's ESCALATE.
        report = orch.run("fix mod.py: it returns one item too few", str(tmp_path), "mod.py")
        assert report.status != RunStatus.ESCALATE

    def test_slice_total_fits_s2_context_budget(self, tmp_path: Path):
        """Dogfood 2026-10-10: the no-gate ablation's repair prompt hit
        16,805 tokens against the llama-server's 16,384-token context →
        400 Bad Request. The S2's prompt budget is a hard ceiling, so the
        total slice context must be capped to fit it with room for the
        system prompt and the generation."""
        from janus.core.orchestrator import _fit_slices
        big = "x = 1\n" * 20_000
        slices = {f"f{i}.py": big for i in range(4)}  # 320K chars total
        fitted = _fit_slices(slices, budget_chars=40_000)
        total = sum(len(v) for v in fitted.values())
        assert total <= 41_000, f"slices exceed budget: {total} chars"
        for path, code in fitted.items():
            assert "...[truncated for context budget]..." in code, path
        # under budget: unchanged
        small = {"a.py": "x = 1\n"}
        assert _fit_slices(small, budget_chars=40_000) == small
