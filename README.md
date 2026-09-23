# Janus

> Two faces, one gate. A terminal coding engine that makes small local models
> punch far above their weight by divorcing *decisions* from *generation*.

Janus splits the coding assistant into two cognitive tiers:

- **System 1 — the gate (Laya).** A non-autoregressive decision model
  ([convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya))
  that answers typed questions with calibrated probabilities in a single
  forward pass. It classifies intent, picks target files/symbols, and decides
  whether to proceed or escalate — it can never emit prose or hallucinate JSON.
- **System 2 — the hand (local LLM).** A compact model (qwen3-4b by default,
  via an OpenAI-compatible endpoint) that receives only Tree-sitter-pruned
  AST slices and must respond in strict `<<<<<<< SEARCH / ======= / >>>>>>> REPLACE`
  patch blocks.
- **The verifier.** A deterministic patch engine (exact → whitespace-normalized
  match, reject otherwise) and a subprocess test runner close the loop, with
  System 1 triaging failures into one-shot repair prompts.

## Status

Scaffold phase. The deterministic core (types, config, patch parser/engine)
is implemented and falsifier-tested; model integrations land next.

## Install

```bash
pip install -e ".[dev]"        # core + tests
pip install -e ".[dev,laya]"   # + System 1 (Laya checkpoint, ~808MB)
```

## Test

```bash
pytest
```

## Layout

```
src/janus/
├── core/        # types, config, orchestrator
├── system1/     # DecisionEngineProtocol + Laya engine
├── system2/     # GenerativeEngineProtocol + local-LLM client
├── context/     # Tree-sitter AST pruner, repo map
├── patcher/     # search/replace parser + applicator (deterministic core)
├── verification/# test runner + failure triage
└── cli.py       # Typer entrypoint
```
