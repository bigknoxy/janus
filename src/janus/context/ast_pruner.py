"""Tree-sitter based AST extraction — the context diet for System 2.

Two operations:

  extract_symbol(source, symbol)  -> the exact code slice for a function or
                                     class (by name), including decorators,
                                     or None if not found.
  skeleton(source)                -> the whole file with every top-level
                                     body replaced by `...`, keeping all
                                     signatures, imports, and assignments.
                                     This is System 1's eyes (repo_map input).

Contract: NEVER raises on arbitrary source text. Tree-sitter is
error-tolerant — malformed input parses to an ERROR-laden tree and simply
yields no extraction. Callers get None / best-effort skeleton.
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

_PYTHON = Language(tspython.language())

_SYMBOL_KINDS = {"function_definition", "class_definition"}

_parser = Parser(_PYTHON)


def _parse_bytes(source: str) -> Node:
    return _parser.parse(source.encode("utf-8", errors="replace")).root_node


def _node_text(source: str, node: Node) -> str:
    return source.encode("utf-8", errors="replace")[node.start_byte : node.end_byte].decode(
        "utf-8", errors="replace"
    )


def find_symbol_node(source: str, symbol: str) -> Node | None:
    """Locate a function/class definition named `symbol` anywhere (incl. methods).

    Breadth-first, first match wins; module-level defs are visited before
    deeper ones. Decorated definitions are matched by their inner
    function/class node; the returned node spans the decorators too.
    """
    root = _parse_bytes(source)
    queue = [root]
    while queue:
        node = queue.pop(0)
        candidate = node
        if node.type == "decorated_definition":
            candidate = node.child_by_field_name("definition")
            if candidate is None:
                queue.extend(node.children)
                continue
        if candidate.type in _SYMBOL_KINDS:
            name = candidate.child_by_field_name("name")
            if name is not None and _node_text(source, name) == symbol:
                return node  # includes decorators when wrapped
        queue.extend(node.children)
    return None


def extract_symbol(source: str, symbol: str) -> str | None:
    """Return the exact source slice for `symbol`, decorators included."""
    if not isinstance(source, str) or not symbol:
        return None
    node = find_symbol_node(source, symbol)
    if node is None:
        return None
    return _node_text(source, node)


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0]


def skeleton(source: str) -> str:
    """Signature-only rendering: every top-level def/class body -> `...`.

    Nested members of classes are also elided (one `...` per class body),
    because the intent is an S1-consumable overview, not navigable code.
    Best-effort on malformed input: tree-sitter's error recovery keeps
    recognizable signatures intact.
    """
    if not isinstance(source, str):
        return ""
    root = _parse_bytes(source)
    src_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    keep: list[str] = []

    cursor_row = 0
    for child in root.children:
        if child.type == "decorated_definition":
            child = child.child_by_field_name("definition") or child
        if child.type in _SYMBOL_KINDS and child.type != "decorated_definition":
            # Preserve any lines between the previous node and this one
            # (imports, module constants, comments).
            keep.extend(src_lines[cursor_row : child.start_point[0]])
            header_start = child.start_point[0]
            body = child.child_by_field_name("body")
            if body is None:
                keep.append(src_lines[header_start])
            else:
                body_row = body.start_point[0]
                # Header may span several rows (decorators, multi-line
                # signatures); keep everything up to the body start.
                for r in range(header_start, body_row):
                    keep.append(src_lines[r])
                body_start_line = src_lines[body_row]
                header_part = body_start_line[: body.start_point[1]]
                indent = " " * (child.start_point[1] + 4)
                keep.append(header_part)
                keep.append(f"{indent}...")
            cursor_row = child.end_point[0] + 1
        # Non-symbol top-level nodes are picked up by the gap-fill above.

    keep.extend(src_lines[cursor_row:])
    result = "\n".join(keep)
    return result.rstrip("\n") + ("\n" if source.endswith("\n") else "")
