"""Run the 18-cell matrix with models pinned to the local cache.

Each cell builds a fresh embedder and, for rerank cells, a fresh cross-encoder.
Both go through `from_pretrained`, which by default phones the HuggingFace hub on
every construction. When that endpoint is slow the call does not fail — it waits,
at 0% GPU with no work done, which looks exactly like a hung process. The models
are already cached, so the offline flags are the correct setting and make each
cell's start deterministic.

    python scripts/run_matrix.py
    python scripts/run_matrix.py --dry-run
"""

from __future__ import annotations

import os
import subprocess
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ORDER = [
    "cell-fixed-dense-plain",
    "cell-fixed-hybrid-plain",
    "cell-fixed-rerank-plain",
    "cell-recursive_parent_child-dense-plain",
    "cell-recursive_parent_child-hybrid-plain",
    "cell-recursive_parent_child-rerank-plain",
    "cell-fixed-dense-contextual_prefix",
    "cell-fixed-hybrid-contextual_prefix",
    "cell-fixed-rerank-contextual_prefix",
    "cell-recursive_parent_child-dense-contextual_prefix",
    "cell-recursive_parent_child-hybrid-contextual_prefix",
    "cell-recursive_parent_child-rerank-contextual_prefix",
    "cell-fixed-dense-late_chunking",
    "cell-fixed-hybrid-late_chunking",
    "cell-fixed-rerank-late_chunking",
    "cell-recursive_parent_child-dense-late_chunking",
    "cell-recursive_parent_child-hybrid-late_chunking",
    "cell-recursive_parent_child-rerank-late_chunking",
]


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    paths = [os.path.join("configs", "grid", name + ".yaml") for name in ORDER]
    missing = [path for path in paths if not os.path.exists(path)]
    if missing:
        print(f"missing cell config(s): {missing}", file=sys.stderr)
        return 1
    command = [sys.executable, "-u", "-m", "ragqa", "grid", "run", *paths]
    if "--dry-run" in argv:
        command.append("--dry-run")
    print("offline: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
