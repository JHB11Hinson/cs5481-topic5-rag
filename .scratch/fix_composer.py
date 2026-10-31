"""Undo the over-broad `.ds-col` flex rule that broke the composer row."""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("ragqa/niceui.py")
text = PATH.read_text(encoding="utf-8")

OLD = (
    ".ds-col {{ display: flex; flex-direction: column; gap: 0 !important; max-width: 720px;\n"
    "  width: 100%; margin: 0 auto; padding: 0 20px; }}"
)
NEW = (
    ".ds-col {{ max-width: 720px; width: 100%; margin: 0 auto; padding: 0 20px; }}\n"
    "/* The transcript is a column whose inherited gap was the remaining 16 px between\n"
    "   messages. The composer row also carries `.ds-col`, so the rule must not force a\n"
    "   direction on it. */\n"
    ".ds-transcript {{ gap: 0 !important; }}"
)
assert OLD in text, "column rule not found"
text = text.replace(OLD, NEW, 1)

OLD_TRANSCRIPT = 'self.transcript = ui.column().classes("ds-col w-full")'
NEW_TRANSCRIPT = 'self.transcript = ui.column().classes("ds-col ds-transcript w-full")'
assert OLD_TRANSCRIPT in text
text = text.replace(OLD_TRANSCRIPT, NEW_TRANSCRIPT, 1)

with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("transcript gap scoped to its own class; composer row keeps its direction")
