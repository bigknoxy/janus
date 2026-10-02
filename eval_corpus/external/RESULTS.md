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
| full, Ollama-S1 decider (2026-10-01) | 0/20 · all ESCALATE | 0 |

- **0 corrupt across all 60 rows** — the rollback doctrine holds on
  external bugs: every failed repair restored byte-for-byte
- **The S1's gate escalates 100% of external prompts** — the calibration
  was built on janus's own prompt style; pydantic-style subjects read as
  too vague. The gate does not transfer, yet.
- **The S2's repair fixes nothing external (0/20, fails safe)** — 4B on
  a 2-core laptop cannot repair pydantic's codebase. SAFE-FAIL is the
  honest outcome: no wrong writes, no corruption.
- **The escalation is structural, not a decider artifact (2026-10-01)**:
  swapping the S1 for Ollama 0.35's systemone decider (tev1:0.8b — a
  different model, 0.7s warm vs ~29s, one external probe PASSED at conf
  0.946) reproduces the same 20/20 ESCALATE on the full arm. The gate's
  margin logic on foreign prompts is the cause, not the Laya checkpoint.
  A decider swap alone does not move it.
- **The calibration opened the door (2026-10-02)**: the nouls on foreign
  prompts are IDENTICAL (0.84 confidence, uniform posture — a 0.01 miss
  under the 0.85 threshold, routing RIGHT). The BCE-objective fit failed
  (picked the flattest T, escalated everything 41/41); the fixed
  objective — minimize the gate's escalation rate + an unsafe penalty,
  subject to route accuracy — fitted **T=0.74**: gate escalation
  32/41 → 12/41, **external 19/20 → 0/20**, route accuracy identical
  (0.878, argmax invariant as designed), unsafe unchanged at 1 (the
  model's raw argmax on one ambiguous prompt — the engine's anchor rule
  escalates it deterministically). The external escalation is now
  calibrated away; the claim re-test runs with the calibration deployed.

## Verdict

The claim "fixes bugs from real histories" **does NOT extend to external
repos at 4B** — it stays janus-scoped. Per the falsifier exit, that is
documented here rather than shipped as a claim. The tooling (miner,
`--python` flag, fixture venv route, event monitor) ships and works;
the corpus stays as infrastructure. **The calibration (T=0.74, measured
2026-10-02) takes external gate escalations from 19/20 to 0/20** — the
remaining levers for the claim re-test: the external eval WITH the
calibration deployed, and a stronger S2 tier (Kaggle corpus curation,
CLM-8B verifier).
