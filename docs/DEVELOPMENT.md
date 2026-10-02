# Development

```bash
git clone https://github.com/bigknoxy/janus && cd janus
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest            # unit + property falsifiers + corpus replay + stub e2e
ruff check src tests dev
```

## The corpus contract

Everything the system learns from real failure becomes **data**:

- Malformed model output → `tests/corpus/*.jsonl` (replayed as standing
  falsifier tests — never transcribed by hand)
- Reproducible bug → `eval_corpus/*.json` (fails red before the fix,
  green after; the harness refuses fixtures that can't fail)

## Eval

```bash
python dev/eval.py --md report.md --json report.json
# modes: full | no-gate | no-repair  (the thesis ablations)
```

Exit 1 on any CORRUPT/INFRA/BAD-FIXTURE row. A nightly cron on the authors'
laptop runs the full matrix — `dev/install_cron.sh` reproduces it on yours.

## S1 calibration

```bash
# in-process (a box with the Laya checkpoint):
python dev/calibrate_s1.py --out dev/calibration.json
# or via an HTTP S1 backend (no checkpoint needed):
python dev/calibrate_s1.py --serve-url http://localhost:11434 \
    --subfolder tev1:0.8b --corpus eval_corpus/external --out dev/calibration.json
```

The fit minimizes the gate's objective (escalation rate + unsafe-routing
penalty, subject to route accuracy). `dev/calibration.json` is a per-box
gitignored artifact the engine reads per decision — deploying it takes
effect immediately, and a STALE one silently contaminates clean eval
comparisons: remove it before trusting a run. Never write it to the repo
while an eval is reading it.

## Live System 1 tests

Skipped by default; on a machine with the Laya package installed:

```bash
JANUS_LAYA_LIVE=1 pytest tests/test_laya_live.py
```

## Conventional commits

Releases are automated (release-please): use `feat:`, `fix:`, `perf:`.
Everything lands via PR to `main`; CI must be green.
