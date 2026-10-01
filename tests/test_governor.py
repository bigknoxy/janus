"""LoadGovernor (JB-3 follow-on): janus must never queue onto a drowning
CPU-bound llama-server. Linux-only read of /proc/loadavg, injected for tests."""

import pytest

from janus.core.governor import LoadGovernor, LoadSaturatedError


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def test_zero_limit_disables_gate():
    LoadGovernor(limit=0.0, read_load=lambda: 99.0).wait()  # never raises


def test_load_below_limit_passes():
    LoadGovernor(limit=4.0, read_load=lambda: 1.2).wait()


def test_load_above_limit_blocks_then_recovers():
    clock = _FakeClock()
    loads = iter([9.0, 9.0, 1.0])
    gov = LoadGovernor(limit=4.0, read_load=lambda: next(loads), timeout_s=120.0, poll_s=10.0)
    gov.wait(clock=clock)
    assert clock.sleeps == [10.0, 10.0]


def test_load_above_limit_times_out_loudly():
    clock = _FakeClock()
    gov = LoadGovernor(limit=4.0, read_load=lambda: 9.0, timeout_s=15.0, poll_s=10.0)
    with pytest.raises(LoadSaturatedError):
        gov.wait(clock=clock)


def test_missing_proc_loadavg_is_noop():
    # non-Linux: read_load default returns None → gate inert, never blocks
    LoadGovernor(limit=4.0).wait()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_orchestrator_governor_saturates_cleanly(tmp_path):
    from janus.core.config import JanusSettings
    from janus.core.orchestrator import PipelineOrchestrator
    from janus.system1.mock_engine import MockDecisionEngine

    class _StubS2:
        def generate_patch(self, prompt, temperature=None):
            raise AssertionError("must never be reached under saturation")

    (tmp_path / "mod.py").write_text("def add(a,b):\n    return a-b\n")
    settings = JanusSettings(
        s2_loadavg_limit=0.5, s2_loadavg_timeout=0.05,  # 0.5<load always; tiny timeout
        max_repair_attempts=0,
    )
    orch = PipelineOrchestrator(
        # the mock derives its decision from the prompt keywords; settings
        # carries the saturation config — never pass a decision positionally
        s1=MockDecisionEngine(settings=settings, confidence=0.99),
        s2=_StubS2(), runner=None, settings=settings,
    )
    import unittest.mock as mock

    from janus.core.governor import LoadSaturatedError

    class _SaturatedGovernor:
        def __init__(self, *args, **kwargs) -> None: ...

        def wait(self, clock: object | None = None) -> None:
            raise LoadSaturatedError("load 9.9 >= 0.5 for > 0s")

    # The governor's read_load default binds _proc_loadavg at import time —
    # patching the module attribute never reaches it (CI-flake root cause:
    # idle runners read load < 0.5 and never saturate). Patch the class:
    # the target here is the orchestrator's clean-exit path, not the
    # governor's own saturation logic (covered by the fake-clock tests).
    with mock.patch("janus.core.orchestrator.LoadGovernor", _SaturatedGovernor):
        rep = orch.run_modify(
            orch._s1.evaluate("fix mod.py", "mod.py :: add"), str(tmp_path)
        )
    from janus.core.orchestrator import RunStatus as RS
    assert rep.status == RS.FAILED_ROLLED_BACK
    assert "load-saturated" in rep.message
    assert (tmp_path / "mod.py").read_text() == "def add(a,b):\n    return a-b\n"
