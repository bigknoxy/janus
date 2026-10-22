# Configuration

Every setting is an env var with the `JANUS_` prefix (or a `.env` file in the
working directory). Sensible defaults target a local Ollama-style endpoint.

| Env var | Default | Meaning |
|---|---|---|
| `JANUS_S1_BACKEND` | `laya` | `laya` (local checkpoint) or `mock` (offline dev) |
| `JANUS_S1_CHECKPOINT` | `convaiinnovations/laya` | HF checkpoint id |
| `JANUS_S1_SUBFOLDER` | `typed-decisions` | checkpoint variant (`""` = English root) |
| `JANUS_S1_SERVE_URL` | _(empty)_ | if set, use `laya-serve` HTTP instead of in-process. **Ollama 0.35+ is a drop-in**: `http://localhost:11434` + `JANUS_S1_SUBFOLDER=tev1:0.8b` — the same `/v1/systemone` schema (noul/choice/score), same decision assembler, zero engine changes. Measured on the laptop: 0.7 s warm per decision vs ~29 s in-process |
| `JANUS_S1_MARGIN_FLOOR` | `0.04` | top1−top2 probability gap below which S1 escalates |
| `JANUS_CONFIDENCE_THRESHOLD` | `0.85` | absolute gate for margin-less engines |
| `JANUS_S2_BASE_URL` | `http://localhost:8080/v1` | OpenAI-compatible endpoint |
| `JANUS_S2_MODEL` | `qwen3-4b` | model name |
| `JANUS_S2_TEMPERATURE` | `0.0` | determinism by default |
| `JANUS_S2_MAX_TOKENS` | `2048` | generation cap |
| `JANUS_S2_TIMEOUT_S` | `300` | per-call timeout |
| `JANUS_S2_LOG_RAW` | _(empty)_ | path to append raw S2 outputs (falsifier corpus fodder) |
| `JANUS_VERIFY_COMMAND` | `pytest -q` | the suite that must pass after a patch |
| `JANUS_VERIFY_TIMEOUT_S` | `120` | verification timeout |
| `JANUS_MAX_REPAIR_ATTEMPTS` | `1` | repair-loop attempts (0–3) |

## S1 calibration (the per-box artifact)

The gate reads two numbers — confidence (threshold 0.85) and top1−top2
margin (floor 0.04). A fitted domain temperature sharpens those numbers
without ever moving the argmax: `sig(logit(p)/T)` is monotonic for T>0,
so the routing is INVARIANT and only the confidence/margin the gate reads
shift. The fit minimizes the **gate's objective** — the escalation rate
plus a heavy unsafe-routing penalty, subject to route accuracy — not
prediction loss (the BCE fit picked the flattest T and escalated
everything; measured 2026-10-01).

- The engine applies the fit **per decision** when `dev/calibration.json`
  is present: missing file, bad JSON, or T==1 → scores unchanged.
  Zero-downtime: the file's appearance takes effect immediately.
- The artifact is **per-box and gitignored** — present only where fitted.
  A stale one silently poisons clean comparisons (measured 2026-10-02):
  check the artifact layer before trusting an eval run.
- Fit it with `dev/calibrate_s1.py` — in-process (checkpoint box) or via
  an HTTP backend, optionally `--corpus eval_corpus/external` so the fit
  sees the foreign-prompt distribution the gate must route. Measured on
  the laptop with the Ollama backend: fitted T=0.74, gate escalation
  32/41 → 12/41, **external 19/20 → 0/20**, route accuracy identical.

## Laptop posture (the reference rig)

A 2-core, 14 GiB laptop serves both faces: Laya on CPU (~808 MB checkpoint,
~200–500 ms/decision in-process) and qwen3-4b via llama-server. The
`janus doctor` command verifies the whole stack. Hard-won guidance:

- Load Laya **in-process single-checkpoint** — multi-checkpoint preload
  consumes the RAM the generation server needs.
- On GPU-less boxes, install CPU-only torch to avoid multi-GB CUDA wheels:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`
- CUDA visibility: prefer `CUDA_VISIBLE_DEVICES=""` over letting torch probe
  an unusable GPU.
