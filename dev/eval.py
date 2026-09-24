#!/usr/bin/env python3
"""Janus eval harness — rates, not anecdotes.

For each fixture in eval_corpus/ and each MODE, the harness:
  1. materializes the fixture in a temp dir (tests red first — asserted),
  2. runs the pipeline (in-process, real S2 endpoint by default),
  3. records outcome: PASSED (suite green, file changed) | SAFE-FAIL
     (rolled back clean) | CORRUPT (file changed without green — never
     acceptable) | INFRA (our bug leaked through).

Modes (the thesis ablations):
  full       — S1 gate + pruning + verify + repair loop
  no-gate    — S1 forced to code_modification (measures the gate)
  no-repair  — repair loop disabled (measures the repair loop value)

Usage:
  python dev/eval.py [--mode MODE]... [--repeat N] [--corpus DIR]
                     [--md report.md] [--json report.json]
Env: JANUS_S2_BASE_URL, JANUS_S1_BACKEND (mock|laya), JANUS_VERIFY_*,
     JANUS_EVAL_WORKERS=1 (fixtures are CPU-bound; keep serial on laptops)
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from janus.core.config import JanusSettings
from janus.core.orchestrator import PipelineOrchestrator, RunStatus
from janus.core.types import IntentType, System1Decision
from janus.system1.mock_engine import MockDecisionEngine
from janus.system2.client import LocalGenerativeEngine
from janus.verification.runner import VerificationRunner

MODES = ("full", "no-gate", "no-repair")


def _materialize(fixture: dict, root: Path) -> None:
    for rel, content in {**fixture["files"], **fixture["tests"]}.items():
        (root / rel).write_text(content, encoding="utf-8")


def _tests_red(root: Path, python: str, verify: str) -> bool:
    proc = subprocess.run(
        f"{python} -m pytest -q {verify}".split(),
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return proc.returncode != 0


def _tests_green(root: Path, python: str, verify: str) -> bool:
    proc = subprocess.run(
        f"{python} -m pytest -q {verify}".split(),
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    return proc.returncode == 0


class _ForceModify:
    """no-gate ablation: the S1 gate is bypassed entirely."""

    def __init__(self, fixture: dict):
        self._files = list(fixture["files"])

    def evaluate(self, user_prompt: str, repo_summary: str) -> System1Decision:
        return System1Decision(
            intent=IntentType.CODE_MODIFICATION,
            confidence=1.0,
            margin=1.0,
            target_files=self._files,
            micro_instruction=user_prompt,
            requires_s2=True,
        )


def run_fixture(fixture: dict, mode: str, settings: JanusSettings, python: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _materialize(fixture, root)
        verify = fixture.get("verify_command", "")
        before = {p: (root / p).read_text() for p in fixture["files"]}

        if not _tests_red(root, python, verify or ""):
            return {"fixture": fixture["name"], "mode": mode, "outcome": "BAD-FIXTURE"}

        run_settings = settings.model_copy(
            update={
                "verify_command": f"{python} -m pytest -q {verify}".strip(),
                "max_repair_attempts": 0 if mode == "no-repair" else settings.max_repair_attempts,
            }
        )
        s1 = (
            _ForceModify(fixture)
            if mode == "no-gate"
            else MockDecisionEngine(settings=run_settings)
            if run_settings.s1_backend == "mock"
            else None
        )
        if s1 is None:
            from janus.system1.laya_engine import LayaDecisionEngine

            s1 = LayaDecisionEngine(run_settings)

        orch = PipelineOrchestrator(
            s1=s1,
            s2=LocalGenerativeEngine(run_settings),
            runner=VerificationRunner(run_settings),
            settings=run_settings,
        )
        t0 = time.time()
        try:
            report = orch.run(fixture["prompt"], str(root), "\n".join(fixture["files"]))
        except Exception as e:  # noqa: BLE001 — internal bugs must be visible
            return {
                "fixture": fixture["name"], "mode": mode,
                "outcome": "INFRA", "error": f"{type(e).__name__}: {e}",
            }
        dt = time.time() - t0

        after = {p: (root / p).read_text() for p in fixture["files"]}
        changed = after != before
        green = _tests_green(root, python, verify or "")

        expect = fixture.get("expect")
        if expect == "ESCALATE_OR_READONLY":
            # Gate fixture: success = no generation spend, no file change.
            if report.status in (RunStatus.ESCALATE, RunStatus.READ_ONLY) and not changed:
                outcome = "PASSED"
            elif changed:
                outcome = "WRONG-INTENT"  # gate failed to hold the line
            else:
                outcome = "WRONG-INTENT"
        elif report.status == RunStatus.PATCHED_VERIFIED and green and changed:
            outcome = "PASSED"
        elif report.status == RunStatus.FAILED_ROLLED_BACK and not changed:
            outcome = "SAFE-FAIL"
        elif changed and not green:
            outcome = "CORRUPT"  # the cardinal sin — never acceptable
        elif report.status == RunStatus.ESCALATE:
            outcome = "ESCALATE"
        else:
            outcome = "SAFE-FAIL"
        return {
            "fixture": fixture["name"], "mode": mode, "outcome": outcome,
            "seconds": round(dt, 1), "status": str(report.status),
            "repair_note": report.repair_note,
        }


def summarize(rows: list[dict]) -> str:
    modes = list(dict.fromkeys(r["mode"] for r in rows))
    out = ["| fixture | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for name in dict.fromkeys(r["fixture"] for r in rows):
        cells = [
            next(
                r["outcome"]
                for r in rows
                if r["fixture"] == name and r["mode"] == m
            )
            for m in modes
        ]
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append("")
    for m in modes:
        sub = [r for r in rows if r["mode"] == m]
        n_pass = sum(r["outcome"] == "PASSED" for r in sub)
        n_corrupt = sum(r["outcome"] == "CORRUPT" for r in sub)
        out.append(f"**{m}**: pass {n_pass}/{len(sub)} · corrupt {n_corrupt}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", action="append", choices=MODES, dest="modes")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--corpus", type=Path, default=Path(__file__).parent.parent / "eval_corpus")
    ap.add_argument("--md", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--fixture", action="append")
    args = ap.parse_args()

    modes = args.modes or list(MODES)
    fixtures = sorted(args.corpus.rglob("*.json"))
    if args.fixture:
        fixtures = [f for f in fixtures if f.stem in args.fixture]
    if not fixtures:
        print("no fixtures found", file=sys.stderr)
        return 2

    settings = JanusSettings()
    python = sys.executable
    rows: list[dict] = []
    for mode in modes:
        for fx_path in fixtures:
            fixture = json.loads(fx_path.read_text())
            for rep in range(args.repeat):
                r = run_fixture(fixture, mode, settings, python)
                r["rep"] = rep
                rows.append(r)
                print(f"[{r['outcome']:>9}] {mode}/{fixture['name']}#{rep} "
                      f"({r.get('seconds', '?')}s)", flush=True)

    md = summarize(rows)
    print("\n" + md)
    if args.md:
        args.md.write_text(md + "\n")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2))

    bad = [r for r in rows if r["outcome"] in {"CORRUPT", "INFRA", "BAD-FIXTURE"}]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
