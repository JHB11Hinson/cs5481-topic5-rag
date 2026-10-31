"""Insert the context guard into the three action callbacks."""

from __future__ import annotations

import pathlib

path = pathlib.Path("ragqa/chainlit_app.py")
text = path.read_text(encoding="utf-8")
for name in ("new_conversation", "show_history", "open_citation"):
    marker = f"async def {name}(action: cl.Action) -> None:\n"
    if marker not in text:
        raise SystemExit(f"callback not found: {name}")
    if f"{marker}    _ensure_steps()\n" in text:
        continue
    text = text.replace(marker, marker + "    _ensure_steps()\n", 1)
with open(path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("guarded callbacks:", text.count("_ensure_steps()"))
