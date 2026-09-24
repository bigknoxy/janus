"""Tree-sitter based AST extraction — the context diet for System 2.

Language-agnostic shared path; per-language specifics live in small
LangSpec registrations. Python and JavaScript ship registered; other
grammars (TS, Go) plug in via register_language() with no changes here.

Two operations:

  extract_symbol(source, symbol)  -> the exact code slice for a function or
                                     class (by name), decorators included,
                                     or None if not found.
  skeleton(source)                -> the file with every symbol body replaced
                                     by `...`, keeping signatures, imports,
                                     and assignments. System 1's eyes.

Contract: NEVER raises on arbitrary source text. Tree-sitter is
error-tolerant — malformed input yields no extraction / a best-effort
skeleton.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from tree_sitter import Language, Node, Parser


@dataclass(frozen=True)
class LangSpec:
    language: Language
    symbol_kinds: frozenset[str]
    # Wrappers that should be unwrapped to find the symbol, keeping the
    # outer span (e.g. Python's decorated_definition).
    wrapper_kinds: frozenset[str] = field(default_factory=frozenset)
    wrapper_field: str = "definition"
    body_field: str = "body"
    # Extra acceptance check per node (e.g. arrow-bearing declarators).
    is_symbol: Callable[[Node], bool] = lambda _n: True
    body_open: str = "..."  # inserted where the body was


_PARSERS: dict[str, Parser] = {}
_SPECS: dict[str, LangSpec] = {}


def register_language(name: str, spec: LangSpec) -> None:
    _SPECS[name] = spec
    _PARSERS[name] = Parser(spec.language)


def registered_languages() -> list[str]:
    return sorted(_SPECS)


def _spec(language: str) -> LangSpec:
    if language not in _SPECS:
        raise ValueError(
            f"unknown language {language!r}; registered: {registered_languages()}"
        )
    return _SPECS[language]


def _parse(source: str, language: str) -> Node:
    return _PARSERS[language].parse(source.encode("utf-8", errors="replace")).root_node


def _node_text(source: str, node: Node) -> str:
    raw = source.encode("utf-8", errors="replace")
    return raw[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _unwrap(spec: LangSpec, node: Node) -> Node:
    if node.type in spec.wrapper_kinds:
        inner = node.child_by_field_name(spec.wrapper_field)
        if inner is not None:
            return inner
    return node


def find_symbol_node(source: str, symbol: str, language: str = "python") -> Node | None:
    """Locate a definition named `symbol` (breadth-first, methods included).

    Wrapper nodes (decorators etc.) match by their inner symbol; the
    returned node spans the wrapper so decorators stay attached.
    """
    spec = _spec(language)
    queue = [_parse(source, language)]
    while queue:
        node = queue.pop(0)
        candidate = _unwrap(spec, node)
        if candidate.type in spec.symbol_kinds and spec.is_symbol(candidate):
            name = candidate.child_by_field_name("name")
            if name is not None and _node_text(source, name) == symbol:
                return node
        queue.extend(node.children)
    return None


def extract_symbol(source: str, symbol: str, language: str = "python") -> str | None:
    """Return the exact source slice for `symbol` (wrappers included)."""
    if not isinstance(source, str) or not symbol:
        return None
    node = find_symbol_node(source, symbol, language)
    if node is None:
        return None
    return _node_text(source, node)


def _first_line(text: str) -> str:
    return text.split("\n", 1)[0]


def skeleton(source: str, language: str = "python") -> str:
    """Signature-only rendering: every top-level symbol body -> `...`.

    Best-effort on malformed input; never raises.
    """
    if not isinstance(source, str):
        return ""
    spec = _spec(language)
    root = _parse(source, language)
    src_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    keep: list[str] = []

    cursor_row = 0
    for child in root.children:
        symbol_node = _unwrap(spec, child)
        if symbol_node.type in spec.symbol_kinds and spec.is_symbol(symbol_node):
            keep.extend(src_lines[cursor_row : child.start_point[0]])
            header_start = child.start_point[0]
            body = symbol_node.child_by_field_name(spec.body_field)
            if body is None:
                keep.append(src_lines[header_start])
            else:
                body_row = body.start_point[0]
                for r in range(header_start, body_row):
                    keep.append(src_lines[r])
                header_part = src_lines[body_row][: body.start_point[1]]
                indent = " " * (child.start_point[1] + 4)
                keep.append(header_part)
                keep.append(f"{indent}{spec.body_open}")
            cursor_row = child.end_point[0] + 1

    keep.extend(src_lines[cursor_row:])
    result = "\n".join(keep)
    return result.rstrip("\n") + ("\n" if source.endswith("\n") else "")


# --- shipped registrations -----------------------------------------------


def _register_python() -> None:
    import tree_sitter_python as tspython

    register_language(
        "python",
        LangSpec(
            language=Language(tspython.language()),
            symbol_kinds=frozenset({"function_definition", "class_definition"}),
            wrapper_kinds=frozenset({"decorated_definition"}),
        ),
    )


def _is_arrow_declarator(node: Node) -> bool:
    return any(
        c.type in {"arrow_function", "function_expression", "generator_function"}
        for c in node.children
    )


def _register_javascript() -> None:
    import tree_sitter_javascript as tsjavascript

    register_language(
        "javascript",
        LangSpec(
            language=Language(tsjavascript.language()),
            symbol_kinds=frozenset(
                {
                    "function_declaration",
                    "class_declaration",
                    "method_definition",
                    "generator_function_declaration",
                    "variable_declarator",  # arrow/const-fn; filtered by is_symbol
                }
            ),
            wrapper_kinds=frozenset({"export_statement"}),
            wrapper_field="declaration",
            is_symbol=lambda n: (
                n.type != "variable_declarator" or _is_arrow_declarator(n)
            ),
            body_open="{ ... }",
        ),
    )


_register_python()
_register_javascript()
