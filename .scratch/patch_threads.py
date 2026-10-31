"""Make the three SQLite caches usable from more than one thread.

The bug this fixes is worth naming, because it cost a live demo. `ChatEngine` is built
once at process start — in the main thread — and it holds an `EmbeddingCache` whose
`sqlite3.Connection` was created there. Chainlit runs `engine.answer` through
`cl.make_async`, i.e. in a worker thread, and every cache read then raised

    sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in
    that same thread.

which the UI showed as nothing at all: the answer never arrived and no error surfaced.
The five recorded demo questions missed it because they called `answer()` directly, in
the thread that built the engine.

Two changes per cache: `check_same_thread=False` on the connection, and a re-entrant
lock around every statement, because a connection may now be *used* from another thread
but must still be *serialised* — sqlite3 objects are not safe for concurrent use even
with the check disabled.
"""

from __future__ import annotations

import pathlib
import re

EMBED_OLD = """        self._conn = sqlite3.connect(path)"""
EMBED_NEW = """        # Built in the main thread, read from Chainlit's worker threads: the check has
        # to come off, and every statement has to be serialised behind a lock.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()"""

CTX_OLD = """        self._conn = sqlite3.connect(path, timeout=30)"""
CTX_NEW = """        self._conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._lock = threading.RLock()"""

LLM_OLD = """        self._conn = sqlite3.connect(path)"""
LLM_NEW = """        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()"""


def write_newline(path: pathlib.Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def lock_methods(path: pathlib.Path, methods: list[str]) -> None:
    """Wrap the body of each named method in `with self._lock:`."""
    text = path.read_text(encoding="utf-8")
    for name in methods:
        pattern = re.compile(
            rf"(    def {name}\(self[^\n]*\n(?:        \"\"\".*?\"\"\"\n)?)((?:        [^\n]*\n)+)",
            re.S,
        )
        match = pattern.search(text)
        if not match:
            raise SystemExit(f"{path}: could not find method {name}")
        head, body = match.group(1), match.group(2)
        indented = "".join(
            ("    " + line if line.strip() else line) for line in body.splitlines(keepends=True)
        )
        replacement = head + "        with self._lock:\n" + indented
        text = text[: match.start()] + replacement + text[match.end():]
    write_newline(path, text)


def main() -> int:
    root = pathlib.Path("ragqa")

    embed = root / "embed.py"
    text = embed.read_text(encoding="utf-8")
    if EMBED_OLD not in text:
        raise SystemExit("embed.py: connection line not found")
    text = text.replace(EMBED_OLD, EMBED_NEW, 1)
    if "import threading" not in text:
        text = text.replace("import sqlite3\n", "import sqlite3\nimport threading\n", 1)
    write_newline(embed, text)
    lock_methods(embed, ["get", "put", "flush", "count", "close"])

    context = root / "context.py"
    text = context.read_text(encoding="utf-8")
    if CTX_OLD not in text:
        raise SystemExit("context.py: connection line not found")
    text = text.replace(CTX_OLD, CTX_NEW, 1)
    if "import threading" not in text:
        text = text.replace("import sqlite3\n", "import sqlite3\nimport threading\n", 1)
    write_newline(context, text)
    lock_methods(context, ["get", "put", "flush", "count", "close"])

    llm = root / "llm.py"
    text = llm.read_text(encoding="utf-8")
    if LLM_OLD not in text:
        raise SystemExit("llm.py: connection line not found")
    text = text.replace(LLM_OLD, LLM_NEW, 1)
    if "import threading" not in text:
        text = text.replace("import sqlite3\n", "import sqlite3\nimport threading\n", 1)
    write_newline(llm, text)
    lock_methods(llm, ["get", "put", "flush", "count", "close"])

    print("patched embed.py, context.py, llm.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
