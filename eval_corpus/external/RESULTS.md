# External-corpus eval: results (JB-1, 2026-09-30)

**Corpus:** 20 curated external fixtures (pydantic fix history, 350
distinct test functions subsampled; 891 raw in `external_raw/`) — mined
by `dev/mine_external.py` (layout auto-detection, diff-touched-test
scoping, parametrized-id-safe filenames).
**Runtime:** laptop qwen3-4b, fixture venv (pydantic-core 2.48.0) via
`--python`; S2 = 4B workhorse, governor on.

## Results

| mode | pass | corrupt |
|---|---|---|
| full (gate + repair) | 0/20 | 0 |
| no-gate (repair only) | 0/20 · 17 SAFE-FAIL | 0 |
| no-repair | 0/20 | 0 |

- **0 corrupt across all 60 rows** — the rollback doctrine holds on
  external bugs: every failed repair restored byte-for-byte
- **The S1's gate escalates 100% of external prompts** — the calibration
  was built on janus's own prompt style; pydantic-style subjects read as
  too vague. The gate does not transfer, yet.
- **The S2's repair fixes nothing external (0/20, fails safe)** — 4B on
  a 2-core laptop cannot repair pydantic's codebase. SAFE-FAIL is the
  honest outcome: no wrong writes, no corruption.

## Verdict

The claim "fixes bugs from real histories" **does NOT extend to external
repos at 4B** — it stays janus-scoped. Per the falsifier exit, that is
documented here rather than shipped as a claim. The tooling (miner,
`--python` flag, fixture venv route, event monitor) ships and works;
the corpus stays as infrastructure for a future era: an S1 calibration
run on external prompts, and a stronger S2 tier (Kaggle corpus curation,
CLM-8B verifier) before the claim is re-tested.
