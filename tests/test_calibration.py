"""_apply_calibration: the domain-temperature consumption in the gate.

Property under test: sig(logit(p)/T) is monotonic for T>0 — the argmax
(routing) is INVARIANT; only the confidence and margin the gate reads move.
"""

from __future__ import annotations

import json


def _scores() -> dict[str, float]:
    # the hedged shape foreign prompts produce: the argmax is already
    # code_modification, but the confidence sits below the gate threshold
    return {
        "code_modification": 0.55,
        "explanation": 0.45,
        "direct_action": 0.30,
        "escalate": 0.20,
    }


def test_calibration_sharpens_confidence_and_margin(tmp_path):
    from janus.system1.laya_engine import _apply_calibration

    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"fitted_temperature": 0.5}))
    scaled = _apply_calibration(_scores(), (cal,))

    assert max(scaled, key=scaled.get) == "code_modification"
    # sharpened: p>0.5 rises, p<0.5 falls, the margin widens
    assert scaled["code_modification"] > 0.55
    assert scaled["explanation"] < 0.45
    raw_margin = 0.55 - 0.45
    assert scaled["code_modification"] - scaled["explanation"] > raw_margin


def test_calibration_preserves_argmax_for_any_temperature(tmp_path):
    from janus.system1.laya_engine import _apply_calibration

    for t in [0.3, 0.5, 0.8, 1.5, 2.0]:
        cal = tmp_path / f"cal-{t}.json"
        cal.write_text(json.dumps({"fitted_temperature": t}))
        scaled = _apply_calibration(_scores(), (cal,))
        assert max(scaled, key=scaled.get) == "code_modification", f"T={t}"


def test_calibration_missing_file_returns_scores_unchanged(tmp_path):
    from janus.system1.laya_engine import _apply_calibration

    scores = _scores()
    assert _apply_calibration(scores, (tmp_path / "nope.json",)) == scores


def test_calibration_t_equals_one_is_noop(tmp_path):
    from janus.system1.laya_engine import _apply_calibration

    cal = tmp_path / "calibration.json"
    cal.write_text(json.dumps({"fitted_temperature": 1.0}))
    assert _apply_calibration(_scores(), (cal,)) == _scores()


def test_calibration_bad_json_returns_scores_unchanged(tmp_path):
    from janus.system1.laya_engine import _apply_calibration

    cal = tmp_path / "calibration.json"
    cal.write_text("not json at all {{{")
    assert _apply_calibration(_scores(), (cal,)) == _scores()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
