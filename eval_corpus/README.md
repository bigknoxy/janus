# Eval corpus

Fixture-as-data. Each `<name>.json`:

```json
{
  "name": "f_offbyone",
  "bug_class": "off-by-one",
  "prompt": "the natural-language request given to janus",
  "files": {"mod.py": "...buggy source..."},
  "tests": {"test_mod.py": "...failing pytest file..."},
  "verify_command": "optional override; default '<python> -m pytest -q'"
}
```

Rules:
- Every fixture must FAIL its tests before the fix and PASS after (the
  harness asserts both — a fixture that can't fail proves nothing).
- Bugs span classes; no two fixtures should be the same mistake.
- New captured failure modes from real traffic grow a fixture (eval) or a
  raw-output replay entry (`tests/corpus/*.jsonl`), never an anecdote.
