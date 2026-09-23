"""Property-based falsifiers (hypothesis).

Universal claims under test:
  C1. parse_patches NEVER raises on arbitrary byte soup (str input) — model
      output is untrusted; worst case is an empty or partial list.
  C2. apply_patch NEVER mutates content when the patch is not found — it
      either returns changed text containing the replacement, or raises
      PatchApplicationError. No silent corruption, no other exception types
      for str inputs.
  C3. Round-trip: a block built by the documented format and re-parsed
      yields an equal PatchBlock.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from janus.core.types import PatchBlock
from janus.patcher.engine import PatchApplicationError, apply_patch
from janus.patcher.parser import (
    DIVIDER_MARKER,
    REPLACE_MARKER,
    SEARCH_MARKER,
    parse_patches,
)

marker_tokens = st.lists(
    st.sampled_from(
        [
            "<", ">", "=", " ", "\n", "\t", "file:", "x", "def", "😀",
            SEARCH_MARKER, DIVIDER_MARKER, REPLACE_MARKER,
        ]
    ),
    max_size=80,
).map(lambda toks: "\n".join(toks))


class TestParserNeverCrashes:
    @settings(max_examples=500)
    @given(marker_tokens)
    def test_c1_arbitrary_soup(self, soup: str):
        result = parse_patches(soup)
        assert isinstance(result, list)
        for block in result:
            assert isinstance(block, PatchBlock)
            # A returned block must always have gone through all three markers.
            assert block.search_block is not None

    @settings(max_examples=200)
    @given(st.text(max_size=500))
    def test_c1_pure_random_text(self, text: str):
        parse_patches(text)  # must not raise


# Chars that act as line separators after normalization are excluded so the
# generated block survives a round trip byte-for-byte.
_SEPARATOR_CHARS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"

safe_line = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",), blacklist_characters=_SEPARATOR_CHARS
    ),
    max_size=40,
)


class TestRoundTrip:
    @settings(max_examples=300)
    @given(
        path=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",), blacklist_characters=_SEPARATOR_CHARS
            ),
            min_size=1,
            max_size=30,
        ),
        search=st.lists(safe_line, max_size=10),
        replace=st.lists(safe_line, max_size=10),
    )
    def test_c3_format_round_trip(self, path: str, search: list[str], replace: list[str]):
        # Lines that collide with markers would be ambiguous by design; skip.
        for line in search + replace:
            if line.strip() in {SEARCH_MARKER, DIVIDER_MARKER, REPLACE_MARKER, ""}:
                return
            if line.strip().startswith("file:"):
                return
        text = (
            f"file: {path}\n{SEARCH_MARKER}\n"
            + "\n".join(search)
            + f"\n{DIVIDER_MARKER}\n"
            + "\n".join(replace)
            + f"\n{REPLACE_MARKER}\n"
        )
        out = parse_patches(text)
        assert len(out) == 1
        assert out[0].search_block == "\n".join(search)
        assert out[0].replace_block == "\n".join(replace)
        assert out[0].file_path == path.strip()


class TestEngineNeverCorrupts:
    @settings(max_examples=300)
    @given(
        content=st.text(max_size=1000),
        search=st.text(min_size=1, max_size=100),
        replace=st.text(max_size=100),
    )
    def test_c2_apply_or_raise_cleanly(self, content: str, search: str, replace: str):
        # A search block containing marker text is parser-domain, exclude here.
        for marker in (SEARCH_MARKER, DIVIDER_MARKER, REPLACE_MARKER):
            if marker in search:
                return
        patch = PatchBlock(file_path="f", search_block=search, replace_block=replace)
        try:
            new_content = apply_patch(content, patch)
        except PatchApplicationError:
            return  # clean rejection — claim satisfied
        # If it applied with replace != search, the content must have changed.
        if replace != search:
            assert new_content != content

    @settings(max_examples=200)
    @given(content=st.text(min_size=1, max_size=300))
    def test_identity_patch_is_noop(self, content: str):
        # Identity is exact modulo CR normalization (\r is canonicalized to \n).
        assume("\r" not in content)
        assume(content.strip() != "")
        # Marker-free, or the exact tier might treat text ambiguously later.
        patch = PatchBlock(file_path="f", search_block=content, replace_block=content)
        try:
            assert apply_patch(content, patch) == content
        except PatchApplicationError:
            pytest.fail("identity patch should always apply exactly")
