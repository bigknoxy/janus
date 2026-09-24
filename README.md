# Janus

> Two faces, one gate. A local-only coding engine where **a decision model
> decides** and **a small LLM generates** — never both.

Janus makes 3B–8B models punch far above their weight by splitting the
coding-assistant problem at its actual seam:

- **System 1 — the gate.** A non-autoregressive decision model
  ([Laya](https://huggingface.co/convaiinnovations/laya)) answers typed
  questions (intent, file targeting) in a single forward pass. It cannot
  emit prose, so it cannot hallucinate JSON. Ambiguity escalates to a human
  instead of spending generation.
- **System 2 — the hand.** A compact local LLM (qwen3-4b by default, any
  OpenAI-compatible endpoint) receives only Tree-sitter-pruned AST slices
  and must reply in strict `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`
  blocks.
- **The safety net.** A deterministic patch engine (exact →
  whitespace-normalized, else reject), real subprocess verification, and
  byte-for-byte rollback on failure — including deleting files a failed run
  created.

Runs entirely on a 2-core, 14 GB laptop. No cloud calls.

## Install

```bash
pip install -e ".[dev]"        # core + tests
pip install -e ".[dev,laya]"   # + System 1 (downloads ~808MB checkpoint once)
```

## Use

```bash
janus doctor --s2-url http://localhost:8081/v1   # check S1, S2, repo map
janus run "fix first_n in mod.py: it returns one item too few" --root .
```

Every run: intent routed by S1 (low margin → escalate), targeted files only,
patch applied in memory, tests run, repair loop on failure, total rollback
on terminal failure.

## Test & eval

```bash
pytest                          # 101 tests, 90%+ coverage gate on the core
python dev/eval.py --md report.md   # fixture-matrix eval with ablations
```

`eval_corpus/` holds fixtures as data. Baseline vs a real qwen3-4b
(2026-09-24): easy tier 8/8, hard tier 5/5 — and the hard tier's ablation
proves the gate earns its keep (5/5 with, 3/5 without).

## Layout

```
src/janus/
├── core/        # types, config, orchestrator (pipeline + rollback)
├── system1/     # DecisionEngineProtocol + Laya (in-proc or laya-serve)
├── system2/     # GenerativeEngineProtocol + OpenAI-compatible client
├── context/     # Tree-sitter AST pruner (registry: python, javascript)
├── patcher/     # search/replace parser + applicator (deterministic)
├── verification/# subprocess runner + failure triage
└── cli.py       # Typer CLI (run, doctor)
```

## Design principles

- Decisions and generation are different cognitive acts — keep them apart.
- Determinism beats intelligence at boundaries: parsing, matching, triage,
  and rollback are code, never models.
- A system that cannot restore byte-parity after failure has no business
  writing to disk. Janus is fuzzed (hypothesis) and audit-hardened (path
  traversal containment, internal-bug transparency) to earn that right.
- Context is scarce: models see slices and skeletons, never whole files.

## Status

Working, self-hosted, and measured. See `eval_corpus/README.md` for the
corpus contract and `eval_report.md` (git history) for runs. Known limits
tracked in the project ISA (not published): laya-serve parity pending
hardware headroom, repair-loop differential fixture pending.

## License

Apache-2.0.
