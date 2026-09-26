#!/usr/bin/env python3
"""Accumulate a fine-tuning corpus from dogfood artifacts.

Every eval row carries (prompt, outcome-by-mode, fixture expect) — the raw
material for a coding-intent decision head. Writes:

  eval_corpus/finetune.jsonl   — one labeled decision per fixture×mode row
  logs/finetune_count.txt     — running count for the Telegram check-in

Designed for the free Kaggle 2xT4 Laya notebook path. Run on the laptop
after a matrix pass, or standalone any time.

    python dev/build_finetune_corpus.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def mode_outcome_to_label(row: dict) -> dict:
    """A labeled decision for the intent head."""
    return {
        "prompt": row.get("_prompt", ""),  # populated when fixture join works
        "fixture": row["fixture"],
        "mode": row["mode"],
        "outcome": row["outcome"],
    }


def main() -> None:
    # Fixture gold labels from corpus
    gold: dict[str, dict] = {}
    for fx in (HERE / "eval_corpus").rglob("*.json"):
        d = json.loads(fx.read_text())
        gold[d["name"]] = d

    rows = 0
    out = HERE / "eval_corpus" / "finetune.jsonl"
    with out.open("w") as fh:
        for log in sorted((HERE / "logs").glob("day*.json")) + sorted(
            (HERE / "logs").glob("dogfood-*.json")
        ):
            for row in json.loads(log.read_text()):
                fx = gold.get(row["fixture"], {})
                label = fx.get("expect", "MODIFY")
                entry = {
                    "prompt": fx.get("prompt", row["fixture"]),
                    "gold_intent": label,
                    "observed_mode": row["mode"],
                    "observed_outcome": row["outcome"],
                }
                fh.write(json.dumps(entry) + "\n")
                rows += 1

    (HERE / "logs" / "finetune_count.txt").write_text(str(rows) + "\n")
    print(f"finetune corpus: {rows} labeled decisions")


if __name__ == "__main__":
    main()
