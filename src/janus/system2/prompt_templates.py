"""Surgical prompt assembly for System 2.

Design rule: the model sees ONLY the AST slice(s) it may edit, the micro
instruction, and the exact output grammar. No whole files, no repo prose.
"""

from janus.patcher.parser import (
    DIVIDER_MARKER,
    REPLACE_MARKER,
    SEARCH_MARKER,
)


def system_prompt() -> str:
    return _SYSTEM


def build_user_prompt(
    instruction: str,
    slices: dict[str, str],
    repair_note: str | None = None,
) -> str:
    """Instruction + the pruned AST slices the model may edit, nothing else.

    `slices` maps file_path -> exact code slice from the AST pruner.
    `repair_note` (from verification triage) tells the model exactly what
    broke in the previous attempt.
    """
    if not slices:
        raise ValueError("refusing to prompt System 2 with zero context slices")
    parts: list[str] = []
    if repair_note:
        parts.append(f"PREVIOUS ATTEMPT FAILED: {repair_note}")
        parts.append("")
    parts.append(f"Task: {instruction}")
    parts.append("")
    for path, code in slices.items():
        parts.append(f"file: {path}")
        parts.append(code)
        parts.append("")
    return "\n".join(parts)


_SYSTEM = f"""You are a surgical code patcher. You output ONLY patch blocks.

Format (one block per edit, no other text):

{SEARCH_MARKER}
<lines copied EXACTLY from the code shown>
{DIVIDER_MARKER}
<the replacement lines>
{REPLACE_MARKER}

Rules:
- The SEARCH section must match the shown code character-for-character,
  including indentation. Never invent context you were not shown.
- Empty {DIVIDER_MARKER} → {REPLACE_MARKER} bodies delete the matched lines.
- One block per edit. No explanations, no apologies, no markdown fencing.
"""

