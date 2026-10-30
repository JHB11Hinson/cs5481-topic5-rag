"""Sample 20 cached prefixes for the ticket-07 audit.

The audit is the only place a human (or the implementing agent, clearly labelled)
reads the generated sentences rather than their effect on a metric. The bar in the
ticket is a fail rate at or below 20%; above that the ticket is not done.

    python scripts/audit_prefixes.py --config configs/ctx-prefix.yaml --sample 20

Writes `notes/prefix-audit.md` with a verdict column left blank and a rubric at the
top, so the audit cannot be graded by the same tool that produced it.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragqa import chunk as chunk_mod  # noqa: E402
from ragqa import config as config_mod  # noqa: E402
from ragqa import corpus  # noqa: E402
from ragqa import context as context_mod  # noqa: E402

RUBRIC = """\
A prefix **passes** when all four hold:

1. **Anchored** — it names the page or section the chunk belongs to, or otherwise
   says where the excerpt sits.
2. **Accurate** — nothing in it contradicts the excerpt or invents a fact the
   excerpt does not carry (a value, a default, a version, a condition).
3. **Discriminating** — it would help a search engine tell this chunk from a
   neighbouring one; a prefix that could sit on any chunk of the page fails.
4. **Clean** — one sentence, no markdown, no elided text, no meta-commentary such
   as "this chunk describes".

A prefix **fails** if any of the four is broken. Record the failing number.
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sample prefixes for the audit.")
    parser.add_argument("--config", default="configs/ctx-prefix.yaml")
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--out", default="notes/prefix-audit.md")
    args = parser.parse_args(argv)

    cfg = config_mod.load(args.config)
    docs = corpus.load_documents(cfg["corpus.source"])
    docs_by_id = {doc["doc_id"]: doc for doc in docs}
    chunks = chunk_mod.build(
        docs,
        cfg["chunk.strategy"],
        int(cfg["chunk.size"]),
        int(cfg["chunk.overlap"]),
        int(cfg["chunk.parent_size"]),
    )
    children = [c for c in chunks if c["kind"] == "child"]
    children.sort(key=lambda c: c["chunk_id"])

    cache = context_mod.PrefixCache(cfg["context.prefix_cache_path"])
    version = f"{cfg['context.prefix_prompt_version']}@{cfg['context.prefix_reasoning_effort'] or 'default'}"
    by_doc: dict = {}
    for child in children:
        by_doc.setdefault(child["doc_id"], []).append(child)

    resolved = []
    for doc_id, doc_chunks in by_doc.items():
        doc_chunks.sort(key=lambda c: c["char_start"])
        for position, chunk in enumerate(doc_chunks):
            before = doc_chunks[position - 1]["text"] if position else ""
            after = doc_chunks[position + 1]["text"] if position + 1 < len(doc_chunks) else ""
            prompt = context_mod.prompt_for(
                doc_id, chunk.get("heading_path", ""), chunk["text"], before, after
            )
            key = context_mod.PrefixCache.key(
                cfg["context.prefix_model"], version, prompt
            )
            prefix = cache.get(key)
            if prefix:
                resolved.append((chunk, prefix))
    resolved.sort(key=lambda pair: pair[0]["chunk_id"])
    if not resolved:
        print("no cached prefixes found: warm the cache first", file=sys.stderr)
        return 1

    step = max(1, len(resolved) // args.sample)
    sample = resolved[::step][: args.sample]

    lines = [
        "# Contextual prefix audit (ticket 07)",
        "",
        f"Sample: {len(sample)} of {len(resolved)} cached prefixes, every {step}th chunk in "
        "`chunk_id` order, so the sample is spread across documents rather than clustered.",
        "",
        f"Model: `{cfg['context.prefix_model']}`, prompt version `{version}`, "
        f"cache `{cfg['context.prefix_cache_path']}`.",
        "",
        "Rubric:",
        "",
        RUBRIC,
        "## Sample",
        "",
        "| # | doc_id | heading | chunk (first 160 chars) | prefix | verdict |",
        "|---|---|---|---|---|---|",
    ]
    for index, (chunk, prefix) in enumerate(sample, start=1):
        excerpt = chunk["text"][:160].replace("|", "\\|").replace("\n", " ")
        heading = (chunk.get("heading_path") or "")[:60].replace("|", "\\|")
        prefix_cell = prefix.replace("|", "\\|")
        lines.append(
            f"| {index} | `{chunk['doc_id']}` | {heading} | {excerpt} | {prefix_cell} | |"
        )
    lines += [
        "",
        "## Verdicts",
        "",
        "Filled in after reading each row against its chunk. `fail` needs the rubric number.",
        "",
        "_(pending)_",
        "",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    print(f"wrote {len(sample)} rows to {args.out}")
    cache.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
