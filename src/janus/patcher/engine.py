"""Deterministic search-and-replace patch applicator.

Matching ladder (in order):
  1. Exact substring match.
  2. Whitespace-normalized line-by-line alignment (leading/trailing
     whitespace per line ignored; interior preserved).
  3. AST-anchored: if the search and replace blocks share exactly one
     symbol definition whose name exists in the file, replace the whole
     AST span of that symbol (indent-drift safe by construction).
  4. PatchApplicationError — no fuzzy guessing beyond that.
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
    try:
        return _apply_normalized(content, patch)
    except PatchApplicationError as e:
        if "ambiguous" in str(e):
            raise  # ambiguity is a final answer, never tier 3
        try:
            return _apply_ast_anchored(content, patch)
        except PatchApplicationError as anchor_e:
            raise PatchApplicationError(
                f"search block not found (exact, normalized, or AST-anchored): "
                f"{anchor_e}"
            ) from e


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


def _code_slices(text: str) -> str:
    """Strip markdown fencing from a model-emitted code blob, if present."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def _apply_ast_anchored(content: str, patch: PatchBlock) -> str:
    """Tier 3: replace by symbol span when text matching failed.

    Deterministic preconditions (any miss → reject):
      - search and replace blocks each contain exactly one detectable symbol
      - the two symbols share a name
      - that name resolves to exactly one definition in the file
    Then the replace block's symbol text swaps into the file's span.
    """
    from janus.context.ast_pruner import (
        extract_symbol,
    )
    from janus.context.ast_pruner import (
        skeleton as _skel,  # noqa: F401  (registry warmup import)
    )

    lang = "python" if patch.file_path.endswith(".py") else None
    search_src = _code_slices(patch.search_block)
    replace_src = _code_slices(patch.replace_block)

    if lang is None:
        raise PatchApplicationError("AST anchoring unsupported for this file type")

    names = []
    for src in (search_src, replace_src):
        # names of symbols the block defines: use skeleton + registry walk
        found = _defined_symbol_names(src, lang)
        if len(found) != 1:
            raise PatchApplicationError("AST anchor needs exactly one defined symbol")
        names.append(found[0])
    if names[0] != names[1]:
        raise PatchApplicationError(
            f"AST anchor symbol mismatch: {names[0]!r} vs {names[1]!r}"
        )

    from janus.context.ast_pruner import find_symbol_node as _find

    node = _find(content, names[0], lang)
    if node is None:
        raise PatchApplicationError("AST anchor symbol not found in file")

    new_def = extract_symbol(replace_src, names[0], lang)
    if new_def is None:
        raise PatchApplicationError("AST anchor replace-block extraction failed")

    raw = content.encode("utf-8", errors="replace")
    replaced = raw[: node.start_byte].decode("utf-8", errors="replace") + new_def
    replaced += raw[node.end_byte :].decode("utf-8", errors="replace")
    return replaced


def _defined_symbol_names(source: str, language: str) -> list[str]:
    """Names of function/class symbols a snippet defines (deduped, ordered)."""

    from janus.context.ast_pruner import _PARSERS, _SPECS  # registry access

    if language not in _PARSERS:
        return []
    spec = _SPECS[language]
    root = _PARSERS[language].parse(source.encode("utf-8", errors="replace")).root_node
    names: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        cand = node
        if node.type in spec.wrapper_kinds:
            inner = node.child_by_field_name(spec.wrapper_field)
            if inner is not None:
                cand = inner
        if cand.type in spec.symbol_kinds and spec.is_symbol(cand):
            nm = cand.child_by_field_name("name")
            if nm is not None:
                raw = source.encode("utf-8", errors="replace")
                name = raw[nm.start_byte : nm.end_byte].decode("utf-8", errors="replace")
                if name not in names:
                    names.append(name)
        stack.extend(node.children)
    return names


def apply_all(content: str, patches: list[PatchBlock]) -> str:
    """Apply a sequence of patches in order; first failure aborts."""
    for patch in patches:
        content = apply_patch(content, patch)
    return content
