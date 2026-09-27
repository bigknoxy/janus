"""LoadGovernor — backpressure for CPU-bound model servers.

Janus's System 2 may run against a tiny box (the laptop: 2 cores, 4-model
fleet). When the machine is drowning, queueing a 155s prefill on top is how
client timeouts and server disconnects get manufactured. The governor reads
/proc/loadavg (Linux-only, no-op elsewhere) and waits politely before any
generation call — every consumer of the orchestrator inherits the courtesy.

Inject `read_load` / clock in tests; a limit of 0.0 disables the gate.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class LoadSaturatedError(RuntimeError):
    """Load stayed above the configured limit beyond timeout."""


def _proc_loadavg() -> float | None:
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


class _Clock:
    def time(self) -> float:
        return time.monotonic()

    def sleep(self, s: float) -> None:
        time.sleep(s)


class LoadGovernor:
    def __init__(
        self,
        limit: float = 4.0,
        timeout_s: float = 600.0,
        poll_s: float = 20.0,
        read_load: Callable[[], float | None] = _proc_loadavg,
    ) -> None:
        self.limit = limit
        self.timeout_s = timeout_s
        self.poll_s = poll_s
        self._read_load = read_load

    def wait(self, clock: object | None = None) -> None:
        if self.limit <= 0:
            return
        c = clock if clock is not None else _Clock()
        deadline = float(c.time()) + self.timeout_s  # type: ignore[attr-defined]
        while True:
            load = self._read_load()
            if load is None or load < self.limit:
                return
            if float(c.time()) >= deadline:  # type: ignore[attr-defined]
                raise LoadSaturatedError(
                    f"load {load:.1f} >= {self.limit:.1f} for > {self.timeout_s:.0f}s"
                )
            c.sleep(self.poll_s)  # type: ignore[attr-defined]
