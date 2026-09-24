"""Repo map: the compact, signature-only overview System 1 sees.

Format is line-oriented: "<relative/path> <flattened skeleton signatures>".
Budget-aware: files are prioritized shallow-first, and the whole map is
capped so it fits inside the English checkpoint's state budget.
"""

import os
from pathlib import Path

from janus.context.ast_pruner import skeleton

_DEFAULT_IGNORES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".hypothesis", ".ruff_cache", ".mypy_cache",
}
_SOURCE_EXTS = {".py"}


def repo_map(root: str, max_chars: int = 6_000, exts: set[str] | None = None) -> str:
    """Walk `root` and render a compact map. Exts defaults to {.py}."""
    exts = exts or _SOURCE_EXTS
    base = Path(root)
    lines: list[str] = []
    budget = max_chars

    candidates: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in _DEFAULT_IGNORES)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.suffix in exts:
                candidates.append(p)

    # Source before tests, shallow first — modules carry the intent
    # signal; test files are noise for targeting (live probe 2026-09-24:
    # test-file fragments exhausted the budget before source appeared).
    def _rank(p: Path) -> tuple[int, int, str]:
        rel = p.relative_to(base)
        is_test = any(
            part.startswith(("test", "tests")) or part.startswith("test_")
            for part in rel.parts
        ) or p.name.startswith("test_")
        return (int(is_test), len(rel.parts), p.name)

    candidates.sort(key=_rank)

    for path in candidates:
        rel = str(path.relative_to(base))
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        sig = _flatten(skeleton(source))
        line = f"{rel} {sig}"[:240]
        if len(line) > budget:
            break
        lines.append(line)
        budget -= len(line) + 1
    return "\n".join(lines)


def _flatten(skel: str) -> str:
    """Collapse a skeleton to structural one-liners: defs, classes, imports
    only. Anything else is noise for the S1 head budget."""
    frags = []
    for ln in skel.splitlines():
        s = ln.strip()
        if s.startswith(("def ", "class ", "async def ", "import ", "from ")):
            frags.append(s[:80])
    return " | ".join(frags)[:240]
