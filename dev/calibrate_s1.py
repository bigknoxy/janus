#!/usr/bin/env python3
"""Domain temperature fitting for System 1 (Laya nouls).

Static per-question temperature scaling on the intent nouls. Fits a scalar
T against the GATE's objective (2026-10-01: minimize the escalation rate
plus a heavy unsafe-routing penalty, subject to the route accuracy not
degrading — the argmax is invariant under T>0), then re-runs the gate to
measure routing accuracy and escalation before/after. Produces
dev/calibration.json consumed by LayaDecisionEngine (if present).

Run on a box with the checkpoint:
    python dev/calibrate_s1.py [--out dev/calibration.json]

or against an HTTP S1 backend (no checkpoint needed):
    python dev/calibrate_s1.py --serve-url http://localhost:11434 \
        --subfolder tev1:0.8b [--corpus eval_corpus/external]

--corpus joins an external fixture dir's prompts to the probe set
(gold=modification, repo-map summaries built the same way the eval builds
them) so the fit sees the foreign-prompt distribution the gate must route.
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
    ap.add_argument(
        "--corpus", type=Path, default=None,
        help="external fixture dir — its prompts (repo-map summaries built the\n"
        "same way the eval builds them) join the probe set, gold=modification",
    )
    ap.add_argument(
        "--serve-url", default=None,
        help="S1 HTTP backend (e.g. Ollama http://localhost:11434);\n"
        "default = in-process Laya checkpoint",
    )
    ap.add_argument("--subfolder", default=None, help="S1 model subfolder for the HTTP backend")
    args = ap.parse_args()

    random.seed(0)
    from janus.context.repo_map import repo_map
    from janus.core.config import JanusSettings
    from janus.system1.laya_engine import LayaDecisionEngine
    from janus.system1.schemas import intent_questions

    settings = JanusSettings()
    if args.serve_url:
        settings = JanusSettings(s1_serve_url=args.serve_url, s1_subfolder=args.subfolder)
    engine = LayaDecisionEngine(settings)

    def predict_raw(state: dict, questions: dict) -> dict:
        # raw nouls — bypass the gate; the calibration fits the T on the
        # unscaled scores the same way the engine will read them
        if engine._agent is not None:
            return engine._agent.predict(state, questions)
        return engine._predict_http(state, questions)

    # (prompt, gold, repo_summary) — the janus probes share REPO; external
    # fixtures get a repo-map summary built from their materialized files
    probes: list[tuple[str, str | None, str]] = [(p, g, REPO) for p, g in PROBES]
    n_external = 0
    if args.corpus:
        import tempfile

        for fx_path in sorted(Path(args.corpus).glob("*.json")):
            fixture = json.loads(fx_path.read_text())
            with tempfile.TemporaryDirectory() as td:
                for rel, content in {**fixture["files"], **fixture["tests"]}.items():
                    fp = Path(td) / rel
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(content)
                repo = repo_map(td)
            probes.append((fixture["prompt"], "intent:code_modification", repo))
            n_external += 1

    raw: list[dict] = []
    for prompt, gold, repo in probes:
        result = predict_raw({"request": prompt, "repository": repo}, intent_questions())
        scores = {k: float(a["noul"]) for k, a in result["answers"].items()}
        is_ext = gold == "intent:code_modification" and repo != REPO
        raw.append({"prompt": prompt, "gold": gold, "scores": scores,
                    "external": bool(n_external and is_ext)})
        parts = " ".join(f"{k.split(chr(58))[1][:6]}={v:.2f}" for k, v in scores.items())
        label = ("EXT" if raw[-1]["external"] else "") + (gold if gold else "AMBIG")
        print(f'  {label:>30} | {parts}')

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

    # the gate's inputs: the escalation-rate helpers + thresholds — needed
    # by both the fit's objective and the report below
    def route_scores(scores: dict, temp: float) -> dict:
        return {k: sig(logit(v) / temp) for k, v in scores.items()}

    def gate_escalates(scores: dict, raw: dict, threshold: float, floor: float) -> bool:
        ranked = sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]
        top = scores[ranked[0]]
        # Dogfood 2026-10-07: the margin floor reads the RAW margin — the
        # calibration's sharpening compresses upper-plateau margins (an
        # artifact of the transform, not new information), so the same S1
        # response must not flip verdicts through the transform. The engine
        # does the same: confidence calibrated, margin raw.
        margin = raw[ranked[0]] - raw[ranked[1]] if len(ranked) >= 2 else 1.0
        return top < threshold or margin < floor

    threshold = settings.confidence_threshold
    floor = getattr(settings, "s1_margin_floor", 0.04)

    # Objective (2026-10-01, the BCE lesson): the fit's objective must be
    # the GATE's objective, not prediction loss. The BCE fit picked the
    # range's flattest edge (T=2.0) and pushed every prompt under the
    # threshold (41/41 escalated). New objective: minimize the escalation
    # rate + a heavy unsafe penalty, subject to the route accuracy not
    # degrading (invariant under T>0, but asserted honestly).
    acc_before = sum(
        route(r["scores"], 1.0) == (r["gold"] or "intent:escalate") for r in raw
    ) / len(raw)

    def unsafe_rate(temp: float) -> float:
        amb = [r for r in raw if r["gold"] is None]
        if not amb:
            return 0.0
        bad = sum(
            1 for r in amb if route(r["scores"], temp) == "intent:code_modification"
        )
        return bad / len(amb)

    best_t, best_obj = 1.0, None
    for t in [x / 100 for x in range(30, 201, 2)]:
        acc = sum(
            route(r["scores"], t) == (r["gold"] or "intent:escalate") for r in raw
        ) / len(raw)
        if acc < acc_before - 1e-9:
            continue
        esc = sum(
            gate_escalates(route_scores(r["scores"], t), r["scores"], threshold, floor)
            for r in raw
        ) / len(raw)
        obj = esc + 5.0 * unsafe_rate(t)
        if best_obj is None or obj < best_obj:
            best_t, best_obj = t, obj

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

    # the REAL metric: the gate's escalation rate on the raw vs scaled
    # scores — the argmax never moves; the confidence+margin do
    for label, pred in (("all", None), ("external", True), ("janus", False)):
        subset = [r for r in raw if pred is None or r["external"] == pred]
        if not subset:
            continue
        esc_before = sum(
            gate_escalates(r["scores"], threshold, floor) for r in subset)
        esc_after = sum(
            gate_escalates(route_scores(r["scores"], best_t), threshold, floor)
            for r in subset)
        print(f"  gate escalation [{label:>8}]: "
              f"{esc_before}/{len(subset)} -> {esc_after}/{len(subset)}")

    out = {
        "fitted_temperature": best_t,
        "objective": round(best_obj, 4) if best_obj is not None else None,
        "bce_before": round(bce(raw, 1.0), 4),
        "bce_after": round(bce(raw, best_t), 4),
        "route_accuracy_before": correct_before / len(raw),
        "route_accuracy_after": correct_after / len(raw),
        "unsafe_modify_after": unsafe_after,
        "n_probes": len(raw),
        "n_external": n_external,
        "backend": args.serve_url or "in-process-laya",
    }
    args.out.write_text(json.dumps(out, indent=2))
    print("\ncalibration:", json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
