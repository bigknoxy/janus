"""P1: replay the harvested corpus — every raw model output captured from
real runs (tests/corpus/*.jsonl) is a standing falsifier case. Totality +
expected parse shape. New harvests append rows; nothing here is transcribed
by hand."""

import json
from pathlib import Path

import pytest

from janus.patcher.engine import PatchApplicationError, apply_patch
from janus.patcher.parser import parse_patches

CORPUS_DIR = Path(__file__).parent / "corpus"


def _rows():
    out = []
    for f in sorted(CORPUS_DIR.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


ROWS = _rows()


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_corpus_totality_and_shape(row: dict):
    blocks = parse_patches(row["raw"])  # must not raise — model output is untrusted
    assert len(blocks) == row["expect_blocks"]
    if "expect_paths_empty" in row:
        assert all((b.file_path == "") == row["expect_paths_empty"] for b in blocks)


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_corpus_engine_safety(row: dict):
    """Applying harvested blocks to content they don't match must reject
    cleanly, never corrupt."""
    for block in parse_patches(row["raw"]):
        if not block.search_block:
            continue
        with pytest.raises(PatchApplicationError):
            apply_patch("def totally_unrelated():\n    pass\n", block)
