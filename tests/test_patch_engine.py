"""Unit tests: patch parser + applicator over the documented contract."""

import pytest

from janus.core.types import PatchBlock
from janus.patcher.engine import PatchApplicationError, apply_all, apply_patch
from janus.patcher.parser import parse_patches

# ----------------------------- parser ---------------------------------


def make_block(search: str, replace: str, path: str = "app/calc.py") -> str:
    return (
        f"file: {path}\n"
        f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE"
    )


class TestParser:
    def test_single_block(self):
        out = parse_patches(make_block("a = 1", "a = 2"))
        assert out == [
            PatchBlock(file_path="app/calc.py", search_block="a = 1", replace_block="a = 2")
        ]

    def test_multiple_blocks_with_chatter(self):
        text = "Sure! Here is the fix:\n" + make_block("x", "y") + "\nAnd also:\n" + make_block(
            "p", "q", "b.py"
        )
        out = parse_patches(text)
        assert [p.file_path for p in out] == ["app/calc.py", "b.py"]

    def test_blank_lines_inside_block_preserved(self):
        out = parse_patches(make_block("a = 1\n\nb = 2", "a = 9\n\nb = 8"))
        assert out[0].search_block == "a = 1\n\nb = 2"

    def test_unclosed_block_yields_nothing(self):
        assert parse_patches("<<<<<<< SEARCH\nfoo\n=======\nbar\n") == []

    def test_missing_divider_yields_nothing(self):
        assert parse_patches("<<<<<<< SEARCH\nfoo\n>>>>>>> REPLACE\n") == []

    def test_nested_search_discards_outer_and_recovers(self):
        text = (
            "<<<<<<< SEARCH\na\n<<<<<<< SEARCH\nb\n=======\nc\n>>>>>>> REPLACE\n"
            + make_block("ok", "fine")
        )
        out = parse_patches(text)
        assert out[-1].search_block == "ok"

    def test_markers_with_surrounding_whitespace(self):
        text = "  <<<<<<< SEARCH  \na\n  =======  \nb\n  >>>>>>> REPLACE  \n"
        out = parse_patches(text)
        assert len(out) == 1

    def test_non_str_raises(self):
        from janus.patcher.parser import PatchParseError

        with pytest.raises(PatchParseError):
            parse_patches(None)  # type: ignore[arg-type]

    def test_bare_divider_inside_content_is_a_documented_collision(self):
        """P2 audit pin: a bare ======= line inside a SEARCH body truncates
        the block at the divider (grammar limitation, deterministic — this
        test pins the behavior so any future grammar hardening is a
        deliberate change, not drift)."""
        raw = (
            "file: m.py\n<<<<<<< SEARCH\ntitle\n=======\nsubtitle\n"
            "=======\ntitle\n==== replaced\n>>>>>>> REPLACE"
        )
        out = parse_patches(raw)
        assert len(out) == 1
        assert out[0].search_block == "title"

    def test_multiline_search_replace(self):
        search = "def f():\n    return 1"
        replace = "def f():\n    return 2\n\ndef g():\n    return 3"
        out = parse_patches(make_block(search, replace))
        assert out[0].replace_block == replace


# ----------------------------- engine ---------------------------------


class TestEngineExact:
    def test_exact_single_match(self):
        content = "a = 1\nb = 2\n"
        patch = PatchBlock(file_path="f", search_block="b = 2", replace_block="b = 3")
        assert apply_patch(content, patch) == "a = 1\nb = 3\n"

    def test_ambiguous_exact_match_rejected(self):
        content = "x = 1\nx = 1\n"
        patch = PatchBlock(file_path="f", search_block="x = 1", replace_block="y = 2")
        with pytest.raises(PatchApplicationError, match="ambiguous"):
            apply_patch(content, patch)

    def test_not_found_rejected(self):
        patch = PatchBlock(file_path="f", search_block="nope", replace_block="y")
        with pytest.raises(PatchApplicationError, match="not found|AST anchor"):
            apply_patch("real content\n", patch)

    def test_empty_search_rejected(self):
        patch = PatchBlock(file_path="f", search_block="", replace_block="y")
        with pytest.raises(PatchApplicationError, match="empty"):
            apply_patch("anything", patch)


class TestEngineNormalized:
    def test_indentation_drift_recovers(self):
        content = "def f():\n    return 1\n"
        patch = PatchBlock(
            file_path="f",
            search_block="        return 1",    # model invented extra indent — not a substring
            replace_block="    return 42",     # we trust the replacement's own indent
        )
        assert apply_patch(content, patch) == "def f():\n    return 42\n"

    def test_ambiguous_normalized_rejected(self):
        content = "    pass\ndef g():\n        pass\n"
        patch = PatchBlock(file_path="f", search_block="pass", replace_block="...")
        with pytest.raises(PatchApplicationError, match="ambiguous"):
            apply_patch(content, patch)


class TestASTAnchored:
    """Tier 3: when text matching fails, anchor by the shared symbol's AST
    span (information the pruner already knows; free, deterministic)."""

    def test_indent_mangled_search_recovers_by_span(self):
        content = "def render(row):\n    out = []\n\n    return row.upper()\n"
        patch = PatchBlock(
            file_path="mod.py",
            search_block="def render(row):\nreturn row.upper()",  # lost indents
            replace_block="def render(row):\n    return row.title()",
        )
        # Tier 2 fails (window mismatch), tier 3 replaces the whole def span.
        out = apply_patch(content, patch)
        assert out == "def render(row):\n    return row.title()\n"
        # span replacement replaces the WHOLE symbol — dead lines die with it

    def test_anchor_requires_shared_symbol(self):
        content = "def a():\n    return 1\n"
        patch = PatchBlock(
            file_path="mod.py",
            search_block="def unmatched_\nxyz",
            replace_block="def b():\n    return 2",
        )
        with pytest.raises(PatchApplicationError):
            apply_patch(content, patch)

    def test_anchor_respects_class_scoping(self):
        content = "class A:\n    def m(self):\n        return 1\n\ndef m():\n    return 'outer'\n"
        patch = PatchBlock(
            file_path="mod.py",
            search_block="def m(self):\n    return 1",
            replace_block="def m(self):\n        return 2",
        )
        out = apply_patch(content, patch)
        assert "return 1" not in out.splitlines()[2] and "return 'outer'" in out


class TestApplyAll:
    def test_sequential_application(self):
        content = "a = 1\nb = 2\n"
        patches = [
            PatchBlock(file_path="f", search_block="a = 1", replace_block="a = 10"),
            PatchBlock(file_path="f", search_block="b = 2", replace_block="b = 20"),
        ]
        assert apply_all(content, patches) == "a = 10\nb = 20\n"

    def test_abort_on_failure(self):
        content = "a = 1\n"
        patches = [
            PatchBlock(file_path="f", search_block="nope", replace_block="x"),
            PatchBlock(file_path="f", search_block="a = 1", replace_block="a = 2"),
        ]
        with pytest.raises(PatchApplicationError):
            apply_all(content, patches)
