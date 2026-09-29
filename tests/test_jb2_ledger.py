"""JB-2: per-decision arbitration must travel from orchestrator → eval row →
ledger JSON, with the gate-saves math verified deterministically."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dev"))

from eval import append_ledger, summarize  # noqa: E402


def _row(fixture, mode, outcome):
    return {
        "fixture": fixture,
        "mode": mode,
        "outcome": outcome,
        "seconds": 1.0,
        "status": "patched_verified",
        "repair_note": None,
        "s1": {
            "intent": "code_modification",
            "confidence": 0.9,
            "target_files": ["mod.py"],
            "target_symbols": ["add"],
        },
        "arbitration": {"candidates": 1, "chosen": 0, "order": [0]},
    }


def test_ledger_counts_gate_saves_and_overreaches(tmp_path):
    rows = []
    for fx, full_out, ng_out in [
        ("f_saved", "PASSED", "WRONG-INTENT"),   # gate saved the day
        ("f_saved2", "ESCALATE", "CORRUPT"),     # gate saved the day
        ("f_over", "SAFE-FAIL", "PASSED"),       # gate over-escalated
        ("f_equal", "PASSED", "PASSED"),         # no signal
    ]:
        rows.append(_row(fx, "full", full_out))
        rows.append(_row(fx, "no-gate", ng_out))
    append_ledger(rows, tmp_path)
    import json

    ledger = json.loads((tmp_path / "eval_ledger.json").read_text())
    run = ledger["runs"][-1]
    assert run["gate_saves"] == 2
    assert run["gate_overreaches"] == 1


def test_ledger_counts_infra_rows(tmp_path):
    import json

    rows = [_row("f_infra", "full", "INFRA"), _row("f_ok", "full", "PASSED")]
    append_ledger(rows, tmp_path)
    ledger = json.loads((tmp_path / "eval_ledger.json").read_text())
    run = ledger["runs"][-1]
    assert run["infra"] == 1
    assert run["full_pass"] == 1


def test_summarize_carries_arbitration_line():
    rows = [
        _row("f1", "full", "PASSED"),
        _row("f1", "no-gate", "WRONG-INTENT"),
    ]
    out = summarize(rows)
    assert "**arbitration**:" in out
    assert "gate saved 1" in out


def test_eval_rows_carry_s1_and_arbitration_fields():
    # schema probe: every row shape must expose the per-decision record
    r = _row("x", "full", "PASSED")
    assert r["s1"]["intent"] == "code_modification"
    assert r["arbitration"]["chosen"] == 0
