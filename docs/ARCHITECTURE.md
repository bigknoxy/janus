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
