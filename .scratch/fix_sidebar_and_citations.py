"""Restyle the sidebar rows and render citations inline as superscripts.

Three defects visible in the screenshot, each with a cause:

1. **A long conversation title ran past the sidebar's right edge.** The row was a flex
   container whose text child had `min-width: 0` set on an inner div, but the element that
   was actually the flex item was the NiceGUI `ui.html` wrapper, which kept
   `min-width: auto` and therefore refused to shrink. The fix is the classic one:
   `flex: 1 1 auto; width: 0; min-width: 0` on the item that must clip.
2. **Too much air between "Manage" and the first date group.** Quasar gives every column
   and row a flex gap; the drawer's containers now carry `gap: 0`, and the group heading's
   own padding supplies the only spacing.
3. **The citation marker appeared twice** — once as text inside the sentence (from
   `render_answer`, which Chainlit needs) and once as a detached button below it. Now the
   markdown is converted to HTML and every `[n]` becomes a clickable superscript in place,
   with a single page-level click handler routed back through NiceGUI's event bus.
"""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("ragqa/niceui.py")
text = PATH.read_text(encoding="utf-8")

# ---- 1. CSS: clipping + tighter sidebar rhythm + inline citation superscript -------
OLD_CSS = """.ds-row-text {{ flex: 1 1 auto; min-width: 0; overflow: hidden; }}"""
NEW_CSS = """.ds-row-text {{ flex: 1 1 auto; width: 0; min-width: 0; overflow: hidden; }}
.ds-cite {{ color: var(--ds-blue-pressed); background: var(--ds-blue-soft); border-radius: 999px;
  padding: 0 5px; margin-left: 2px; font-size: 11px; font-weight: 600; cursor: pointer;
  vertical-align: super; line-height: 1; }}
.ds-cite:hover {{ background: var(--ds-blue); color: #fff; }}"""
assert OLD_CSS in text, "row-text rule not found"
text = text.replace(OLD_CSS, NEW_CSS, 1)

OLD_MANAGE = """.ds-manage {{ padding: 0 2px; margin: 4px 0 0; }}"""
NEW_MANAGE = """.ds-manage {{ padding: 0 2px; margin: 2px 0 -2px; height: 22px; }}"""
assert OLD_MANAGE in text
text = text.replace(OLD_MANAGE, NEW_MANAGE, 1)

OLD_GROUP = """.ds-group {{ font-size: 11px; color: var(--ds-text-3); padding: 10px 8px 2px; font-weight: 500; }}"""
NEW_GROUP = """.ds-group {{ font-size: 11px; color: var(--ds-text-3); padding: 8px 8px 2px;
  font-weight: 500; line-height: 16px; }}"""
assert OLD_GROUP in text
text = text.replace(OLD_GROUP, NEW_GROUP, 1)

# ---- 2. the row's clickable text becomes one flex item that is allowed to shrink ----
OLD_ROW_TEXT = """            html(
                f'<div class="ds-row-text" data-conversation="{row["id"]}">'
                f'<span class="ds-title">{title}</span>'
                f'<span class="ds-meta">{turns} message(s)</span>'
                "</div>"
            ).on("click", lambda _event, conversation=row["id"]: self._open(conversation))"""
NEW_ROW_TEXT = """            html(
                f'<div class="ds-row-text" data-conversation="{row["id"]}">'
                f'<span class="ds-title">{title}</span>'
                f'<span class="ds-meta">{turns} message(s)</span>'
                "</div>"
            ).style("flex: 1 1 auto; width: 0; min-width: 0; overflow: hidden").on(
                "click", lambda _event, conversation=row["id"]: self._open(conversation)
            )"""
assert OLD_ROW_TEXT in text
text = text.replace(OLD_ROW_TEXT, NEW_ROW_TEXT, 1)

# ---- 3. citations render in place; the detached chip row goes ----------------------
OLD_BUBBLE = '''    def _bubble_assistant(self, markdown: str, payload: Optional[Dict[str, Any]]) -> None:
        claims = (payload or {}).get("claims") or []
        abstained = bool((payload or {}).get("abstained"))
        with self.transcript:
            with ui.column().classes("ds-msg w-full gap-0"):
                ui.markdown(markdown or "").classes("ds-assistant")
                if claims or abstained:
                    with ui.row().classes("ds-cites"):
                        for claim in claims:
                            html(
                                f'<div class="ds-cite" data-marker="{claim["marker"]}">'
                                f'{claim["marker"]}</div>'
                            ).on("click", lambda _event, citation=claim["citation"]: self._open_citation(citation))
                        if abstained:
                            html('<div class="ds-badge">not in the documentation</div>')
        self.body.run_method("scrollTo", {"top": 10 ** 6, "behavior": "smooth"})'''
NEW_BUBBLE = '''    def _bubble_assistant(self, markdown: str, payload: Optional[Dict[str, Any]]) -> None:
        claims = (payload or {}).get("claims") or []
        abstained = bool((payload or {}).get("abstained"))
        for claim in claims:
            self.citation_index[claim["marker"]] = claim["citation"]
        with self.transcript:
            with ui.column().classes("ds-msg w-full gap-0"):
                html(_answer_html(markdown or "")).classes("ds-assistant")
                if abstained:
                    html('<div class="ds-badge">not in the documentation</div>')
        self.body.run_method("scrollTo", {"top": 10 ** 6, "behavior": "smooth"})

    def _open_citation_marker(self, marker: str) -> None:
        """A click on an inline superscript. The marker is resolved against the
        conversation currently on screen, so a replayed answer stays clickable."""
        citation = self.citation_index.get(marker)
        if citation is None:
            ui.notify(f"Source {marker} is not in this conversation", type="warning")
            return
        self._open_citation(citation)'''
assert OLD_BUBBLE in text
text = text.replace(OLD_BUBBLE, NEW_BUBBLE, 1)

# ---- 4. index state, event bus wiring, and the markdown-to-HTML helper -------------
OLD_STATE = """        self.selected: set = set()
        self.manage = False
        self.busy = False"""
NEW_STATE = """        self.selected: set = set()
        self.manage = False
        self.busy = False
        # marker -> citation payload for the conversation on screen. Rebuilt on open and
        # extended on every answer, so an inline superscript can be resolved without
        # re-reading the transcript.
        self.citation_index: Dict[str, Dict[str, Any]] = {}"""
assert OLD_STATE in text
text = text.replace(OLD_STATE, NEW_STATE, 1)

OLD_OPEN = """        self.transcript.clear()
        turns = self.store.messages(conversation_id)
        self.welcome.set_visibility(not turns)"""
NEW_OPEN = """        self.transcript.clear()
        self.citation_index = {}
        turns = self.store.messages(conversation_id)
        self.welcome.set_visibility(not turns)"""
assert OLD_OPEN in text
text = text.replace(OLD_OPEN, NEW_OPEN, 1)

OLD_TAIL = """        self.question.on("keydown.enter", self._ask)"""
NEW_TAIL = """        # Inline superscripts are plain DOM inside one HTML element, so a delegated
        # listener plus NiceGUI's event bus is what lets them call back into Python
        # without a component per marker.
        ui.on("open_citation", lambda event: self._open_citation_marker(str(event.args.get("marker"))))
        ui.add_body_html(
            \"\"\"
            <script>
            document.addEventListener('click', (event) => {
              const node = event.target.closest('.ds-cite');
              if (node && node.dataset.marker) {
                emitEvent('open_citation', {marker: node.dataset.marker});
              }
            });
            </script>
            \"\"\"
        )
        self.question.on("keydown.enter", self._ask)"""
assert OLD_TAIL in text
text = text.replace(OLD_TAIL, NEW_TAIL, 1)

HELPER = '''

CITATION = re.compile(r"\\[(\\d+)\\]")


def _answer_html(markdown: str) -> str:
    """Markdown to HTML with every `[n]` turned into a clickable superscript.

    The marker stays where the sentence put it, which is what the text says and what a
    reader expects; a separate row of buttons underneath duplicated it and read as a
    stray control. Mistune is already a dependency of the environment and needs no
    browser build step.
    """
    import mistune

    body = mistune.html(markdown or "")
    return CITATION.sub(
        lambda match: (
            f'<sup class="ds-cite" data-marker="[{match.group(1)}]">'
            f'[{match.group(1)}]</sup>'
        ),
        body,
    )


'''
marker = "def _escape(text: str) -> str:"
assert marker in text
text = text.replace(marker, HELPER.strip() + "\n\n\n" + marker, 1)

if "import re" not in text.split("from nicegui")[0]:
    text = text.replace("import os\nimport threading", "import os\nimport re\nimport threading", 1)

PATH.write_text(text, encoding="utf-8", newline="\n") if False else None
with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
    handle.write(text)
print("niceui.py restyled: shrinking rows, tighter rhythm, inline citation superscripts")
