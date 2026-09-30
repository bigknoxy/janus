# Architecture

```
            your request
                 │
        ╔════════▼════════╗
        ║   🚪 SYSTEM 1   ║   Laya decision head — typed answers only
        ║   intent?       ║   margin-gated escalation
        ║   which files?  ║   (path-mention pins first, nouls as fallback)
        ╚════════╤════════╝
                 │ code_modification with confident margin
                 ▼
        ┌──────────────────┐
        │ Tree-sitter      │   AST slices of target symbols only
        │ pruner           │   (whole files never enter the prompt)
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │  ✋ SYSTEM 2      │   compact local LLM (qwen3-4b default)
        │  patch grammar    │   file:/<<<<<<< SEARCH/=======/>>>>>>>
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ deterministic    │   exact → whitespace-normalized match
        │ patch engine     │   else reject; path-traversal contained
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │ verification     │   real pytest in a subprocess
        │ + triage         │   failure → `Fix: <assertion> at f:line`
        └────────┬─────────┘
                 ▼
        pass → done ✓   fail → 1 repair attempt →
        still failing → ROLLBACK, byte-for-byte (creations deleted)
```

## Hard boundaries

- **Decisions never generate; generation never decides.** System 1's output
  is a typed `System1Decision`; System 2's output is parsed, never executed
  as instructions.
- **Determinism at the seams.** Parsing, matching, triage, rollback — all
  plain code with fuzz coverage (hypothesis), not model calls.
- **The model is untrusted input.** Patch paths are containment-checked
  against the repo root before any write.

## The /context registry

`context/ast_pruner.py` holds a `LangSpec` registry — Python and JavaScript
ship; a new grammar is a registration, not a refactor.

## Arbitration (JB-2)

The gate's correctness is reported per-decision, not on aggregate. Every
eval row carries S1's decision record (`s1.intent/confidence/targets`) and,
when the patch-ranker ran (JB-3), its arbitration record
(`candidates/chosen/order`). From a full matrix run — which includes the
gate-removed ablation — the ledger derives two counters:

- **gate_saves**: fixtures where bypassing the gate produced a worse
  outcome (CORRUPT / WRONG-INTENT / FAILED) than the gated run
- **gate_overreaches**: fixtures where the gate blocked a fix the
  ungated run would have landed (no-gate PASSED, full SAFE-FAIL/ESCALATE)

These render on the public Ledger so the anchor-gate doctrine stays
observable, and `gate_overreaches > 0` is the early-warning that the gate
has become a liar.

## System One backends (2026-09-30)

The S1's protocol seam is real: the laya-serve backend was built
Jev-compatible, and Ollama 0.35's `/v1/systemone` endpoint speaks the
same schema — so **Ollama is a drop-in S1 backend** (`JANUS_S1_SERVE_URL`
+ `JANUS_S1_SUBFOLDER` = the decision model), with zero engine changes.
Measured on the laptop: tev1:0.8b classifies correctly at 0.7 s warm per
decision (vs ~29 s in-process) with real top1−top2 probability gaps —
which means the anchor rule and margin floor finally operate on a true
distribution rather than a parsed guess.
