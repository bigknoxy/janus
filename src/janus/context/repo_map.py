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


def repo_map(root: str, max_chars: int = 3_000, exts: set[str] | None = None) -> str:
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

    # Shallow paths first — top-level modules carry the intent signal.
    candidates.sort(key=lambda p: (len(p.relative_to(base).parts), p.name))

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
    """Collapse a skeleton to signature-ish one-liner fragments."""
    frags = [
        ln.strip()
        for ln in skel.splitlines()
        if ln.strip()
        and not ln.strip().startswith(("#", "...", '"""', "'''"))
        and (ln.strip().startswith(("def ", "class ", "async def ")) or "=" in ln)
    ]
    return " | ".join(frags)[:200]
