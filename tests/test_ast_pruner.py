"""Unit tests: Tree-sitter symbol extraction and skeleton pruning."""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from janus.context.ast_pruner import extract_symbol, skeleton

SAMPLE = '''"""Module docstring."""
import os

CONSTANT = 42


def helper(x):
    return x + 1


@decorator
def calculate_tax(amount, rate=0.2):
    """Docstring."""
    total = amount * (1 + rate)
    return total


class Order:
    kind = "sale"

    def total(self):
        return calculate_tax(self.amount)


def tail():
    pass
'''


class TestExtractSymbol:
    def test_plain_function(self):
        out = extract_symbol(SAMPLE, "helper")
        # Slice spans exactly the def node; no trailing newline included.
        assert out == "def helper(x):\n    return x + 1"

    def test_decorated_function_keeps_decorator(self):
        out = extract_symbol(SAMPLE, "calculate_tax")
        assert out.startswith("@decorator")
        assert "return total" in out

    def test_class_full_body(self):
        out = extract_symbol(SAMPLE, "Order")
        assert "def total(self):" in out

    def test_method_by_name(self):
        out = extract_symbol(SAMPLE, "total")
        assert out.lstrip().startswith("def total(self):")

    def test_missing_symbol_is_none(self):
        assert extract_symbol(SAMPLE, "nope") is None

    def test_empty_inputs_are_none(self):
        assert extract_symbol("", "f") is None
        assert extract_symbol(SAMPLE, "") is None


class TestSkeleton:
    def test_signatures_survive_bodies_elided(self):
        out = skeleton(SAMPLE)
        assert "def helper(x):" in out
        assert "def calculate_tax(amount, rate=0.2):" in out
        assert "class Order:" in out
        assert "return x + 1" not in out
        assert "return total" not in out

    def test_imports_and_constants_survive(self):
        out = skeleton(SAMPLE)
        assert "import os" in out
        assert "CONSTANT = 42" in out
        assert "Module docstring" in out

    def test_decorators_survive(self):
        assert "@decorator" in skeleton(SAMPLE)

    def test_ellipsis_present(self):
        assert "..." in skeleton(SAMPLE)

    def test_multiline_signature(self):
        src = "def f(a,\n      b=1):\n    return a + b\n"
        out = skeleton(src)
        assert "def f(a," in out
        assert "b=1):" in out
        assert "return a + b" not in out

    def test_empty_and_garbage(self):
        assert skeleton("") == ""
        out = skeleton("def broken(:\n")
        assert isinstance(out, str)  # best-effort, never raises


class TestPrunerNeverCrashes:
    """C4: the pruner is total — any byte soup yields None / a string."""

    pythonish = st.lists(
        st.sampled_from(
            [
                "def f(x):", "class A:", "    return 1", "import os", "@dec",
                "(", ")", ":", "    ", "\n", "async def g():", "yield", "😀",
                "'''", '"x"', "\\", "\x00",
            ]
        ),
        max_size=60,
    ).map("".join)

    @settings(max_examples=500)
    @given(pythonish)
    def test_skeleton_total(self, soup: str):
        assert isinstance(skeleton(soup), str)

    @settings(max_examples=500)
    @given(source=pythonish, symbol=st.text(max_size=20))
    def test_extract_total(self, source: str, symbol: str):
        assume("\x00" not in symbol or True)  # null bytes must still be safe
        out = extract_symbol(source, symbol)
        assert out is None or (isinstance(out, str) and out != "")

    @settings(max_examples=300)
    @given(source=pythonish)
    def test_extract_never_returns_empty_for_hit(self, source: str):
        out = extract_symbol(source, "f")
        assert out is None or len(out) > 0
