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
