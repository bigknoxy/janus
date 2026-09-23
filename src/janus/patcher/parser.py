"""Extraction of System 2 patch blocks from raw model output.

Format (one or more blocks; anything outside a block is ignored as chatter):

    file: <path>
    <<<<<<< SEARCH
    <exact lines from original AST slice>
    =======
    <replacement lines>
    >>>>>>> REPLACE

Contract: NEVER raises on arbitrary model output. Malformed input yields an
empty list (or the well-formed subset). Only wholly structural violations that
indicate a caller bug raise PatchParseError.
"""

from janus.core.types import PatchBlock

SEARCH_MARKER = "<<<<<<< SEARCH"
DIVIDER_MARKER = "======="
REPLACE_MARKER = ">>>>>>> REPLACE"
FILE_PREFIX = "file:"


class PatchParseError(Exception):
    """Structural violation indicating caller misuse, not bad model output."""


def _is_search(line: str) -> bool:
    return line.strip() == SEARCH_MARKER


def _is_replace(line: str) -> bool:
    return line.strip() == REPLACE_MARKER


def split_lines(text: str) -> list[str]:
    """Canonical line split: normalize CR/CRLF to LF, split on LF only.

    Shared with the engine so parser output and file content are always
    aligned on the same line boundaries (str.splitlines() would also split
    on exotic separators like \x1e or \u2028, corrupting both sides).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_patches(text: str) -> list[PatchBlock]:
    """Parse all well-formed patch blocks from model output.

    Partial, nested, unclosed, or otherwise mangled blocks are skipped rather
    than raising — model output is untrusted by definition.
    """
    if not isinstance(text, str):
        raise PatchParseError(f"expected str, got {type(text).__name__}")

    lines = split_lines(text)
    patches: list[PatchBlock] = []
    pending_file: str | None = None
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith(FILE_PREFIX) and not _in_block(lines, i):
            pending_file = stripped[len(FILE_PREFIX):].strip() or None
            i += 1
            continue

        if _is_search(line):
            block, consumed = _read_block(lines, i)
            if block is not None:
                search, replace = block
                patches.append(
                    PatchBlock(
                        file_path=pending_file or "",
                        search_block=search,
                        replace_block=replace,
                    )
                )
            # Skip past whatever we consumed (whole block, or to end on malformed).
            i += consumed
            pending_file = None
            continue

        i += 1

    return patches


def _in_block(lines: list[str], idx: int) -> bool:
    """Cheap lookbehind: is this line already inside an open SEARCH block?"""
    depth = 0
    for prev in lines[:idx]:
        if _is_search(prev):
            depth += 1
        elif _is_replace(prev):
            depth = max(0, depth - 1)
    return depth > 0


def _read_block(lines: list[str], start: int) -> tuple[tuple[str, str] | None, int]:
    """Read one SEARCH..REPLACE block starting at `start` (the SEARCH line).

    Returns ((search, replace), lines_consumed). On any malformation returns
    (None, lines_consumed) where consumed reaches the end of the mangled run
    so the scanner doesn't re-interpret interior marker lines as new blocks.
    """
    i = start + 1
    search_lines: list[str] = []
    replace_lines: list[str] = []
    phase = "search"

    while i < len(lines):
        line = lines[i]
        if _is_search(line):
            # Nested SEARCH: the outer block is malformed; abandon it.
            return None, i - start
        if line.strip() == DIVIDER_MARKER and phase == "search":
            phase = "replace"
            i += 1
            continue
        if _is_replace(line):
            if phase != "replace":
                # No divider seen: malformed.
                return None, i - start + 1
            return ("\n".join(search_lines), "\n".join(replace_lines)), i - start + 1
        (search_lines if phase == "search" else replace_lines).append(line)
        i += 1

    # Unclosed block: discard cleanly.
    return None, i - start
