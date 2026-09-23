"""Deterministic search-and-replace patch applicator.

Matching ladder (in order):
  1. Exact substring match.
  2. Whitespace-normalized line-by-line alignment (leading/trailing
     whitespace per line ignored; interior preserved).
  3. PatchApplicationError — no fuzzy guessing beyond that.
"""

from janus.core.types import PatchBlock
from janus.patcher.parser import split_lines


class PatchApplicationError(Exception):
    """The patch could not be matched against the file content."""


def _normalize(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines]


def apply_patch(content: str, patch: PatchBlock) -> str:
    """Apply one PatchBlock to `content`, returning the new content."""
    if not isinstance(content, str):
        raise PatchApplicationError(f"content must be str, got {type(content).__name__}")
    if not isinstance(patch, PatchBlock):
        raise PatchApplicationError(f"patch must be PatchBlock, got {type(patch).__name__}")

    if patch.search_block == "":
        raise PatchApplicationError("empty search block")

    # Normalize line endings so CR-bearing content and patches compare cleanly.
    def _cr_free(s: str) -> str:
        return s.replace("\r\n", "\n").replace("\r", "\n")

    content = _cr_free(content)
    patch = patch.model_copy(
        update={
            "search_block": _cr_free(patch.search_block),
            "replace_block": _cr_free(patch.replace_block),
        }
    )

    # Tier 1: exact match.
    if patch.search_block in content:
        occurrences = content.count(patch.search_block)
        if occurrences > 1:
            raise PatchApplicationError(
                f"search block is ambiguous ({occurrences} exact matches)"
            )
        return content.replace(patch.search_block, patch.replace_block, 1)

    # Tier 2: whitespace-normalized line alignment.
    return _apply_normalized(content, patch)


def _apply_normalized(content: str, patch: PatchBlock) -> str:
    file_lines = split_lines(content)
    if file_lines and file_lines[-1] == "":  # trailing newline artifact
        file_lines.pop()
    search_lines = split_lines(patch.search_block)
    norm_search = _normalize(search_lines)
    span = len(search_lines)

    matches: list[int] = []
    for start in range(0, len(file_lines) - span + 1):
        window = _normalize(file_lines[start : start + span])
        if window == norm_search:
            matches.append(start)

    if not matches:
        raise PatchApplicationError("search block not found (exact or normalized)")
    if len(matches) > 1:
        raise PatchApplicationError(
            f"search block is ambiguous ({len(matches)} normalized matches)"
        )

    start = matches[0]
    replace_lines = split_lines(patch.replace_block)
    new_lines = file_lines[:start] + replace_lines + file_lines[start + span :]
    trailing = "\n" if content.endswith("\n") else ""
    # (replace_lines already split; empty replace deletes the matched span)
    return "\n".join(new_lines) + trailing


def apply_all(content: str, patches: list[PatchBlock]) -> str:
    """Apply a sequence of patches in order; first failure aborts."""
    for patch in patches:
        content = apply_patch(content, patch)
    return content
