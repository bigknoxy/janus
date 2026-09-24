"""ISC-4: regression corpus of REAL qwen3-4b outputs harvested from live
runs (2026-09-24, dev/e2e_real_model.sh). The parser/engine must stay total
over all of them; the orchestrator-level rescues are exercised separately.
"""

import pytest

from janus.core.orchestrator import _whole_slice_fallback
from janus.core.types import PatchBlock
from janus.patcher.engine import PatchApplicationError, apply_patch
from janus.patcher.parser import parse_patches

# Harvest 1: perfect grammar, missing `file:` header.
RAW_NO_HEADER = (
    "<<<<<<< SEARCH\ndef discount(price, pct):\n"
    "    return price - pct  # BUG: ignores percentage scaling\n"
    "=======\ndef discount(price, pct):\n"
    "    return price - (price * pct / 100)  # Apply percentage discount\n"
    ">>>>>>> REPLACE"
)

# Harvest 2: no markers at all — `file:` header + whole corrected slice.
RAW_NO_MARKERS = (
    "file: mod.py\ndef first_n(items, n):\n"
    "    return items[:n]  # Fixed: correct off-by-one error"
)


class TestHarvestedTotality:
    @pytest.mark.parametrize("raw", [RAW_NO_HEADER, RAW_NO_MARKERS])
    def test_parser_never_raises(self, raw: str):
        result = parse_patches(raw)
        assert isinstance(result, list)

    def test_headerless_block_parses_with_empty_path(self):
        out = parse_patches(RAW_NO_HEADER)
        assert len(out) == 1 and out[0].file_path == ""

    def test_whole_slice_fallback_rescues_markerless_output(self):
        slices = {"mod.py": "def first_n(items, n):\n    return items[: n - 1]"}
        patches = _whole_slice_fallback(RAW_NO_MARKERS, slices)
        assert len(patches) == 1
        patched = apply_patch(slices["mod.py"], patches[0])
        assert "items[:n]" in patched

    def test_fallback_refuses_ambiguous_targets(self):
        slices = {"a.py": "x = 1", "b.py": "x = 1"}
        assert _whole_slice_fallback(RAW_NO_MARKERS, slices) == []

    def test_harvest_1_applies_against_unique_file(self):
        content = "def discount(price, pct):\n    return price - pct  # BUG\n"
        patch = PatchBlock(
            file_path="mod.py",
            search_block="def discount(price, pct):\n    return price - pct  # BUG",
            replace_block="def discount(price, pct):\n    return price - (price * pct / 100)",
        )
        assert "pct / 100" in apply_patch(content, patch)
        with pytest.raises(PatchApplicationError):
            apply_patch("def unrelated():\n    pass\n", patch)
