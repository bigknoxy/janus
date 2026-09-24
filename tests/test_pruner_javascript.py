"""ISC-7: JavaScript grammar through the same language registry — no
Python-specific code in the shared path."""

from hypothesis import given, settings
from hypothesis import strategies as st

from janus.context.ast_pruner import (
    extract_symbol,
    registered_languages,
    skeleton,
)

JS_SAMPLE = '''import { tax } from "./rates.js";

export function calcTax(amount, rate = 0.2) {
  const total = amount * (1 + rate);
  return Math.round(total * 100) / 100;
}

const helper = (x) => x * 2;

class Order {
  constructor(amount) {
    this.amount = amount;
  }

  total() {
    return calcTax(this.amount);
  }
}
'''


class TestRegistry:
    def test_both_languages_registered(self):
        assert set(registered_languages()) == {"python", "javascript"}

    def test_unknown_language_raises_cleanly(self):
        try:
            extract_symbol("x", "f", language="cobol")
        except ValueError as e:
            assert "cobol" in str(e)
        else:
            raise AssertionError("expected ValueError")


class TestJSExtraction:
    def test_function_declaration(self):
        out = extract_symbol(JS_SAMPLE, "calcTax", language="javascript")
        assert out is not None and out.startswith("export function calcTax")
        assert "Math.round" in out

    def test_class_declaration_includes_methods(self):
        out = extract_symbol(JS_SAMPLE, "Order", language="javascript")
        assert out is not None and "total()" in out

    def test_method_by_name(self):
        out = extract_symbol(JS_SAMPLE, "total", language="javascript")
        assert out is not None and out.lstrip().startswith("total() {")

    def test_arrow_function_bound_to_const(self):
        out = extract_symbol(JS_SAMPLE, "helper", language="javascript")
        assert out is not None and "=>" in out

    def test_missing_symbol_is_none(self):
        assert extract_symbol(JS_SAMPLE, "nope", language="javascript") is None


class TestJSSkeleton:
    def test_signatures_survive_bodies_elided(self):
        out = skeleton(JS_SAMPLE, language="javascript")
        assert "function calcTax(amount, rate = 0.2)" in out
        assert "class Order" in out
        assert "Math.round" not in out
        assert "return calcTax(this.amount)" not in out

    def test_import_survives(self):
        assert 'import { tax } from "./rates.js";' in skeleton(
            JS_SAMPLE, language="javascript"
        )

    def test_empty_and_garbage(self):
        assert skeleton("", language="javascript") == ""
        assert isinstance(skeleton("function {{{", language="javascript"), str)


class TestJSNeverCrashes:
    jsish = st.lists(
        st.sampled_from(
            ["function f() {", "}", "class A", "=>", "const x =", "\n", "import",
             "(", "😀", "\x00", "{ ... }"]
        ),
        max_size=60,
    ).map("".join)

    @settings(max_examples=300)
    @given(jsish)
    def test_skeleton_total(self, soup: str):
        assert isinstance(skeleton(soup, language="javascript"), str)

    @settings(max_examples=300)
    @given(source=jsish, symbol=st.text(max_size=16))
    def test_extract_total(self, source: str, symbol: str):
        out = extract_symbol(source, symbol, language="javascript")
        assert out is None or (isinstance(out, str) and out != "")
