# JANUS

```
                                 _______
                            .---'|███████|'---.
                           /     |███████|     \
                          |      ¯¯¯|▒|¯¯¯      |
                          |   (🚪    |▒|    ✋)  |
                          |   past   |▒| future |
                          |   decides|▒|generates|
                           \         |▒|        /
                            '.______|▒|______.'
                              the gate stands
```

[![CI](https://github.com/bigknoxy/janus/actions/workflows/ci.yml/badge.svg)](https://github.com/bigknoxy/janus/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/bigknoxy/janus)](https://github.com/bigknoxy/janus/releases)
[![docs](https://img.shields.io/badge/docs-bigknoxy.github.io%2Fjanus-c9962e)](https://bigknoxy.github.io/janus/)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

**A two-faced coding engine.** System 1 decides (a calibrated, non-generative
decision model — Laya). System 2 generates (a compact local LLM). Deterministic
code guards everything in between. Runs entirely on a laptop; no cloud calls.

## One line in

```sh
curl -fsSL https://raw.githubusercontent.com/bigknoxy/janus/main/install.sh | sh
```

## One line out

```sh
curl -fsSL https://raw.githubusercontent.com/bigknoxy/janus/main/uninstall.sh | sh
```

## Watch it work

```console
$ janus run "fix first_n in mod.py: it returns one item too few" --root .
╭──────────────── 🚪 System 1 ────────────────╮
│ intent      code_modification               │
│ confidence  0.90                            │
│ files       mod.py                          │
╰─────────────────────────────────────────────╯
╭──────────────── ⚡ patched_verified ────────╮
│ 1 patch block(s)                            │
│ verify: exit 0                              │
╰─────────────────────────────────────────────╯
```

## Why it works when raw small models don't

| layer | job | failure mode it deletes |
|---|---|---|
| **Gate (S1)** | intent + targeting, typed & calibrated | hallucinated plans, prose-shaped "JSON" |
| **Pruner** | Tree-sitter AST slices only | context rot, whole-file paste |
| **Hand (S2)** | one patch grammar | freeform code dumps |
| **Engine** | exact→normalized match, else reject | silent mis-patches |
| **Verifier** | real tests, real subprocess | "looks right to me" |
| **Rollback** | byte-parity restore, creations deleted | scars from failed runs |

Measured vs a real qwen3-4b: **0 corrupt states across 45+ matrix runs**;
gate ablation shows gate-trap prompts escaping when the gate is removed
(5/7 vs 7/7); repair ablation shows hidden-contract bugs unfixable without
the loop (0/3 without, 3/3 with). Full ledger: [the docs site](https://bigknoxy.github.io/janus/).

## Docs

- [Architecture](docs/ARCHITECTURE.md) — the two faces, hard boundaries
- [Configuration](docs/CONFIGURATION.md) — env vars, low-resource posture
- [Development](docs/DEVELOPMENT.md) — corpus contract, eval, falsifiers
- [Security](SECURITY.md) — threat model and the containment ladder

## The name

Janus, Roman god of gates and beginnings — two faces, one looking back, one
forward. One face judges what must happen; the other writes what will.
Every ending here is verified; every beginning is earned.

Apache-2.0.
