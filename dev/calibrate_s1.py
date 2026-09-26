#!/usr/bin/env python3
"""Domain temperature fitting for System 1 (Laya nouls).

Static per-question temperature scaling on the intent nouls. Fits a scalar
T minimizing binary log-loss on a labeled probe corpus, then re-runs the
gate to measure routing accuracy before/after. Produces
dev/calibration.json consumed by LayaDecisionEngine (if present).

Run on a box with the checkpoint:
    python dev/calibrate_s1.py [--out dev/calibration.json]
"""

import argparse
import json
import math
import random
from pathlib import Path

# Gold-labeled probe corpus: (prompt, gold_intent_or_none_for_ambiguous)
REPO = "calc.py def calculate_tax(amount, rate)\napp/order.py class Order\nmod.py def add(a, b)"

PROBES = [
    # code_modification — clear
    ("fix the tax calculation bug in calc.py", "intent:code_modification"),
    ("add type hints to the parser module", "intent:code_modification"),
    ("refactor _filter_dict_recursively in matchers.py", "intent:code_modification"),
    ("update add(a, b) in mod.py to actually add", "intent:code_modification"),
    ("implement a guard clause in safe_div", "intent:code_modification"),
    ("rename calculate_tax to compute_tax", "intent:code_modification"),
    ("fix parse_rate: commas are thousands separators", "intent:code_modification"),
    ("add a docstring to the Order class", "intent:code_modification"),
    # explanation — clear
    ("explain how patches are applied", "intent:explanation"),
    ("what does the Order class do?", "intent:explanation"),
    ("how does the intent gate work?", "intent:explanation"),
    ("describe the difference between add and calculate_tax", "intent:explanation"),
    ("is the discount formula in calc.py correct? just answer", "intent:explanation"),
    # direct_action — clear
    ("run the test suite", "intent:direct_action"),
    ("git push origin main", "intent:direct_action"),
    ("execute pytest -q and show me the output", "intent:direct_action"),
    # ambiguous / vague — gold = should NOT route to modification
    ("it's broken, make it work", None),
    ("can you do the thing?", None),
    ("the app feels slow", None),
    ("something is off", None),
    ("help?", None),
]

QUESTION_KEYS = [
    "intent:code_modification",
    "intent:explanation",
    "intent:direct_action",
    "intent:escalate",
]


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "calibration.json")
    args = ap.parse_args()

    random.seed(0)
    from janus.core.config import JanusSettings
    from janus.system1.laya_engine import LayaDecisionEngine
    from janus.system1.schemas import intent_questions

    engine = LayaDecisionEngine(JanusSettings())
    raw: list[dict] = []
    for prompt, gold in PROBES:
        result = engine._agent.predict({"request": prompt, "repository": REPO}, intent_questions())
        scores = {k: float(a["noul"]) for k, a in result["answers"].items()}
        raw.append({"prompt": prompt, "gold": gold, "scores": scores})
        parts = " ".join(f"{k.split(chr(58))[1][:6]}={v:.2f}" for k, v in scores.items())
        label = gold if gold else 'AMBIG'
        print(f'  {label:>26} | {parts}')

    def route(scores: dict, temp: float):
        scaled = {k: sig(logit(v) / temp) for k, v in scores.items()}
        return max(scaled, key=scaled.get)

    def bce(scores_list, temp: float) -> float:
        loss = 0.0
        n = 0
        for row in scores_list:
            for k in QUESTION_KEYS:
                p = sig(logit(row["scores"][k]) / temp)
                y = 1.0 if (row["gold"] == k) else 0.0
                if row["gold"] is None:
                    y = 1.0 if k == "intent:escalate" else 0.0
                loss += -(y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9)))
                n += 1
        return loss / max(n, 1)

    best_t, best_loss = 1.0, None
    for t in [x / 100 for x in range(30, 201, 2)]:
        loss = bce(raw, t)
        if best_loss is None or loss < best_loss:
            best_t, best_loss = t, loss

    correct_before = correct_after = 0
    unsafe_after = 0
    for row in raw:
        top_raw = route(row["scores"], 1.0)
        top_cal = route(row["scores"], best_t)
        gold = row["gold"] or "intent:escalate"
        correct_before += top_raw == gold
        correct_after += top_cal == gold
        # unsafe = ambiguous routed to a writing intent
        if row["gold"] is None and top_cal == "intent:code_modification":
            unsafe_after += 1

    out = {
        "fitted_temperature": best_t,
        "bce_before": round(bce(raw, 1.0), 4),
        "bce_after": round(best_loss, 4),
        "route_accuracy_before": correct_before / len(raw),
        "route_accuracy_after": correct_after / len(raw),
        "unsafe_modify_after": unsafe_after,
        "n_probes": len(raw),
    }
    args.out.write_text(json.dumps(out, indent=2))
    print("\ncalibration:", json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
