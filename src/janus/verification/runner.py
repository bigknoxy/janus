"""Subprocess verification: run the project's test/lint command, bounded by
a hard timeout, always returning a typed VerificationResult (never raising
for a failing command — failure IS the data)."""

import subprocess
import sys

from janus.core.config import JanusSettings
from janus.core.types import VerificationResult


class VerificationRunner:
    def __init__(self, settings: JanusSettings | None = None) -> None:
        self._settings = settings or JanusSettings()

    def run(self, cwd: str, command: str | None = None) -> VerificationResult:
        cmd = command or self._settings.verify_command
        # A bare `pytest` resolves against the inherited PATH, which misses a
        # venv-installed janus (the venv's bin/ is not on PATH unless the
        # caller activated it — measured in real use, 2026-10-02). Route it
        # through the interpreter janus itself runs under.
        if cmd.split()[0] == "pytest":
            cmd = f"'{sys.executable}' -m {cmd}"
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self._settings.verify_timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            return VerificationResult(
                passed=False,
                exit_code=-1,
                stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
                stderr=f"verification timed out after {self._settings.verify_timeout_s}s",
            )
        return VerificationResult(
            passed=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
