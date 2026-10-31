"""Collapse the inherited flex gaps and set the sidebar/message rhythm explicitly.

Measured from the screenshot, not guessed: logo -> button -> Manage -> Today were three
consecutive ~30 px gaps, and the user bubble sat 67 px above the answer. Both come from
the same cause — Quasar/NiceGUI give every column and row a flex gap, my earlier selector
did not beat it, and I had added paddings on top. The rule now is: zero the inherited gap
inside the drawer with high specificity, then state every intentional space once.
"""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("ragqa/niceui.py")
text = PATH.read_text(encoding="utf-8")

OLD = """.q-drawer .nicegui-column, .q-drawer .nicegui-row {{ gap: 0 !important; }}"""
NEW = """.q-drawer__content, .q-drawer__content .nicegui-column, .q-drawer__content .nicegui-row,
.q-drawer__content .column, .q-drawer__content .row,
.q-drawer .nicegui-column, .q-drawer .nicegui-row,
.q-drawer .column, .q-drawer .row {{ gap: 0 !important; }}
.q-drawer__content > *, .q-drawer__content .nicegui-column > *,
.q-drawer__content .nicegui-row > * {{ margin-top: 0 !important; margin-bottom: 0 !important; }}"""
assert OLD in text, "gap rule not found"
text = text.replace(OLD, NEW, 1)

RHYTHM = {
    ".ds-brand {{ display: flex; align-items: center; gap: 8px; padding: 12px 2px 8px; }}":
        ".ds-brand {{ display: flex; align-items: center; gap: 8px; padding: 4px 2px 2px !important; }}",
    """.ds-new {{ width: 100%; border: 1px solid var(--ds-divider) !important; border-radius: 999px !important;
  background: var(--ds-canvas) !important; color: var(--ds-text) !important; font-weight: 500;
  padding: 8px 12px !important; box-shadow: none !important; }}""":
        """.ds-new {{ width: 100%; border: 1px solid var(--ds-divider) !important; border-radius: 999px !important;
  background: var(--ds-canvas) !important; color: var(--ds-text) !important; font-weight: 500;
  padding: 6px 12px !important; box-shadow: none !important; margin: 8px 0 0 !important;
  min-height: 32px !important; }}""",
    ".ds-manage {{ padding: 0 2px; margin: 2px 0 -2px; height: 22px; }}":
        ".ds-manage {{ padding: 0 2px; margin: 6px 0 0 !important; height: 18px !important; }}",
    """.ds-group {{ font-size: 11px; color: var(--ds-text-3); padding: 8px 8px 2px;
  font-weight: 500; line-height: 16px; }}""":
        """.ds-group {{ font-size: 11px; color: var(--ds-text-3); padding: 6px 8px 1px;
  font-weight: 500; line-height: 14px; margin: 0 !important; }}""",
    """.ds-row {{ display: flex; align-items: center; gap: 6px; width: 100%; overflow: hidden;
  border-radius: 10px; padding: 6px 8px; cursor: pointer; }}""":
        """.ds-row {{ display: flex; align-items: center; gap: 6px; width: 100%; overflow: hidden;
  border-radius: 10px; padding: 4px 8px; cursor: pointer; margin: 1px 0 !important; }}""",
    ".ds-msg {{ display: flex; margin: 18px 0; }}":
        ".ds-msg {{ display: flex; margin: 9px 0; }}",
    """.ds-assistant {{ width: 100%; font-size: 15px; line-height: 1.65; color: var(--ds-text); }}""":
        """.ds-assistant {{ width: 100%; font-size: 15px; line-height: 1.65; color: var(--ds-text); }}
.ds-assistant p, .ds-assistant ul, .ds-assistant ol {{ margin: 0 !important; }}
.ds-assistant ul, .ds-assistant ol {{ padding-left: 20px; }}
.ds-assistant li {{ margin: 0; }}
.ds-assistant > :first-child {{ margin-top: 0 !important; }}
.ds-assistant > :last-child {{ margin-bottom: 0 !important; }}""",
    ".ds-col {{ max-width: 720px; width: 100%; margin: 0 auto; padding: 0 20px; }}":
        ".ds-col {{ max-width: 720px; width: 100%; margin: 0 auto; padding: 0 20px; }}\n"
        ".q-drawer__content {{ padding: 6px 8px !important; }}",
}

for old, new in RHYTHM.items():
    if old not in text:
        raise SystemExit(f"rule not found: {old[:70]}")
    text = text.replace(old, new, 1)

with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("spacing rules rewritten: inherited gaps zeroed, rhythm stated once")
