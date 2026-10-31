"""Kill the last inherited gap in the transcript, and stop bulleting a single claim."""

from __future__ import annotations

import pathlib

NICE = pathlib.Path("ragqa/niceui.py")
text = NICE.read_text(encoding="utf-8")

OLD_COL = ".ds-col {{ max-width: 720px; width: 100%; margin: 0 auto; padding: 0 20px; }}"
NEW_COL = (
    ".ds-col {{ display: flex; flex-direction: column; gap: 0 !important; max-width: 720px;\n"
    "  width: 100%; margin: 0 auto; padding: 0 20px; }}"
)
assert OLD_COL in text
text = text.replace(OLD_COL, NEW_COL, 1)

OLD_MSG = ".ds-msg {{ display: flex; margin: 9px 0; }}"
NEW_MSG = ".ds-msg {{ display: flex; margin: 8px 0; }}"
assert OLD_MSG in text
text = text.replace(OLD_MSG, NEW_MSG, 1)
with open(NICE, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("transcript gap zeroed")

DEMO = pathlib.Path("ragqa/demo.py")
text = DEMO.read_text(encoding="utf-8")
OLD = """    lines = [f"- {claim['text']} {claim['marker']}" for claim in verified]"""
NEW = """    if len(verified) == 1:
        # One claim is an answer, not a list: a bullet in front of a single sentence is
        # the visual grammar of a report, not of a chat reply.
        lines = [f"{verified[0]['text']} {verified[0]['marker']}"]
    else:
        lines = [f"- {claim['text']} {claim['marker']}" for claim in verified]"""
assert OLD in text
text = text.replace(OLD, NEW, 1)
with open(DEMO, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("single-claim answer is now a paragraph")
