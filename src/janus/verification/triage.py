"""Failure triage: stderr/stdout → a one-line repair note for System 2.

Deterministic by design (regex + last-match heuristics), not a model call:
extracting `<error> at <file>:<line>` from a stack trace is a parsing task,
and every saved inference keeps the loop tight and reproducible.
"""

import re

from janus.core.types import VerificationResult

_PY_LOC = re.compile(r'File "([^"]+)", line (\d+)')
_ERROR_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception)|AssertionError)\b.*")
_PYTEST_FAIL = re.compile(r"^(FAILED|ERROR)\s+\S+::\S+")
_ASSERT_DETAIL = re.compile(r"^E\s+")


def triage_failure(result: VerificationResult, project_root: str | None = None) -> str:
    """Compact the most relevant failure into `Fix: <error> at <file>:<line>`.

    Prefers the LAST in-project traceback frame (deepest user code), then
    the last error-looking line. Falls back to the raw tail when nothing
    recognizable is found — the note must never be empty.
    """
    text = f"{result.stderr}\n{result.stdout}"
    lines = [ln for ln in text.splitlines() if ln.strip()]

    file_at_line = ""
    for m in _PY_LOC.finditer(text):
        path, lineno = m.group(1), m.group(2)
        if project_root is None or project_root in path or not path.startswith("/"):
            file_at_line = f" at {path}:{lineno}"

    error_line = ""
    for ln in reversed(lines):
        if _ERROR_LINE.match(ln.strip()):
            error_line = ln.strip()
            break

    # Pytest short-summary + assertion detail carry the actual signal;
    # '1 failed in 0.11s' is decorative (harvested 2026-09-24: a repair loop
    # starved on exactly that line).
    details = [
        ln.strip()
        for ln in lines
        if _PYTEST_FAIL.match(ln.strip()) or _ASSERT_DETAIL.match(ln.strip())
    ][-4:]
    if details:
        error_line = (error_line + "; " if error_line else "") + " | ".join(
            dict.fromkeys(details)
        )

    if not error_line and lines:
        error_line = lines[-1].strip()
    if not error_line:
        error_line = f"exit code {result.exit_code} with no output"

    return f"Fix: {error_line}{file_at_line}"[:700]
