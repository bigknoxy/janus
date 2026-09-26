# Configuration

Every setting is an env var with the `JANUS_` prefix (or a `.env` file in the
working directory). Sensible defaults target a local Ollama-style endpoint.

| Env var | Default | Meaning |
|---|---|---|
| `JANUS_S1_BACKEND` | `laya` | `laya` (local checkpoint) or `mock` (offline dev) |
| `JANUS_S1_CHECKPOINT` | `convaiinnovations/laya` | HF checkpoint id |
| `JANUS_S1_SUBFOLDER` | `typed-decisions` | checkpoint variant (`""` = English root) |
| `JANUS_S1_SERVE_URL` | _(empty)_ | if set, use `laya-serve` HTTP instead of in-process |
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
