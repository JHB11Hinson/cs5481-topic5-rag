"""Capture the five demo questions once, from the real run configuration.

Run from the worktree root: `python .scratch/capture_demo.py <config> <out.json>`
Prints each rendered answer and writes the raw responses as JSON, so
`notes/demo-script.md` records output that actually happened.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from ragqa import config as config_mod, demo

QUESTIONS = [
    ("A001", "What state does a Vault server start in, and what can it not do in that state?"),
    ("A004", "What address and port does the Vault dev server listen on by default?"),
    ("A007", "According to the entropy augmentation table, what is the root key encrypted by, and what does it encrypt?"),
    ("A009", "During operator init the root key is split into shards; how does that relate to the sealed state a server starts in?"),
    ("U008", "If my AppRole secret ID has a 30-minute TTL, what will the agent auto-auth token TTL be?"),
]


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/real_llm.yaml"
    out_path = sys.argv[2] if len(sys.argv) > 2 else ".scratch/demo-capture.json"
    engine = demo.ChatEngine.from_config(config_path)
    print(engine.describe(), flush=True)

    captured = {"config": config_path, "config_name": engine.config_name, "items": []}
    for item_id, question in QUESTIONS:
        response = engine.answer(question)
        captured["items"].append({"item_id": item_id, "response": response})
        print("\n" + "=" * 78, flush=True)
        print(f"[{item_id}] {question}", flush=True)
        print("-" * 78, flush=True)
        print(demo.render_answer(response), flush=True)
        sys.stdout.flush()

    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(captured, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    print(f"\nwrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
