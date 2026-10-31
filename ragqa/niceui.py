"""A DeepSeek-styled RAG screen in NiceGUI.

The design is not invented: it follows the published DeepSeek chat design tokens — one
accent (`#4D6BFE`), a white canvas, a 280 px sidebar, blue-soft user bubbles with an
asymmetric 18/18/4/18 radius, assistant replies with **no** bubble at full contrast, a
25 pt composer pill, and a centred 720 pt reading column. The wordmark follows the same
pattern the product uses: blue mark, then the name with its last token tinted.

What the earlier attempts got wrong, and this file does not:

- **Nothing on screen that is machinery.** No chunk ids, no scores, no latency, no error
  classes. They live in `payload` and surface only in the source drawer.
- **A code block never reaches a reader.** `demo._prose_excerpt` strips fences and JSON
  before display; an abstention says one sentence and names the closest page.
- **A reader's answer is Markdown.** Rendering it as plain text is what showed `**` on
  screen.
- **One question at a time.** The index is single-tenant (embedded Qdrant, one GPU).

    python -m ragqa serve --config configs/... --backend nice --port 8200
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Dict, List, Optional

from nicegui import run, ui

from . import demo, history as history_mod

ANSWER_LOCK = threading.Lock()
HISTORY_ENV = "RAGQA_DEMO_HISTORY"
DEFAULT_HISTORY = "data/demo/history.sqlite"

BLUE = "#4D6BFE"
BLUE_PRESSED = "#3B57E0"
BLUE_SOFT = "#EBEFFF"
CANVAS = "#FFFFFF"
SURFACE = "#F5F6F8"
DIVIDER = "#E4E6EB"
TEXT = "#1A1B1E"
TEXT_2 = "#6A6B70"
TEXT_3 = "#9A9BA0"

WHALE = f"""
<svg viewBox="0 0 48 48" width="26" height="26" aria-hidden="true">
  <path fill="{BLUE}" d="M7.5 27.5c0-6.4 5.6-11 12.4-11 4.4 0 8 1.9 10.4 5.1l6.2-4.6c.9-.7 1.9.1 1.7 1.1l-1.4 7.3 1.4 7.3c.2 1-.8 1.8-1.7 1.1l-6.2-4.6c-2.4 3.2-6 5.1-10.4 5.1-6.8 0-12.4-4.6-12.4-11z"/>
  <circle cx="16.5" cy="24.5" r="1.9" fill="{CANVAS}"/>
</svg>
"""

CSS = f"""
:root {{
  --ds-blue: {BLUE};
  --ds-blue-pressed: {BLUE_PRESSED};
  --ds-blue-soft: {BLUE_SOFT};
  --ds-canvas: {CANVAS};
  --ds-surface: {SURFACE};
  --ds-divider: {DIVIDER};
  --ds-text: {TEXT};
  --ds-text-2: {TEXT_2};
  --ds-text-3: {TEXT_3};
}}
body, .nicegui-content {{ background: var(--ds-canvas); color: var(--ds-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue", Arial, sans-serif; }}
.nicegui-content {{ padding: 0 !important; gap: 0 !important; }}
.q-drawer {{ background: var(--ds-canvas) !important; overflow-x: hidden; }}
.q-drawer--left {{ border-right: 1px solid var(--ds-divider) !important; }}
.q-drawer--right {{ border-left: 1px solid var(--ds-divider) !important; }}
/* NiceGUI/Quasar give every column and row a flex gap; inside a 280 px sidebar that
   gap is what pushed "Today" a visible distance below "Manage". Zero it here and pay
   for spacing deliberately, with the paddings below. */
.q-drawer__content, .q-drawer__content .nicegui-column, .q-drawer__content .nicegui-row,
.q-drawer__content .column, .q-drawer__content .row,
.q-drawer .nicegui-column, .q-drawer .nicegui-row,
.q-drawer .column, .q-drawer .row {{ gap: 0 !important; }}
.q-drawer__content > *, .q-drawer__content .nicegui-column > *,
.q-drawer__content .nicegui-row > * {{ margin-top: 0 !important; margin-bottom: 0 !important; }}
.ds-brand {{ display: flex; align-items: center; gap: 8px; padding: 4px 2px 2px !important; }}
.ds-wordmark {{ font-size: 17px; font-weight: 700; letter-spacing: -.2px; }}
.ds-wordmark span {{ color: var(--ds-blue); }}
.ds-new {{ width: 100%; border: 1px solid var(--ds-divider) !important; border-radius: 999px !important;
  background: var(--ds-canvas) !important; color: var(--ds-text) !important; font-weight: 500;
  padding: 6px 12px !important; box-shadow: none !important; margin: 8px 0 0 !important;
  min-height: 32px !important; }}
.ds-new:hover {{ background: var(--ds-surface) !important; }}
.ds-manage {{ padding: 0 2px; margin: 6px 0 0 !important; height: 18px !important; }}
.ds-group {{ font-size: 11px; color: var(--ds-text-3); padding: 6px 8px 1px;
  font-weight: 500; line-height: 14px; margin: 0 !important; }}
.ds-row {{ display: flex; align-items: center; gap: 6px; width: 100%; overflow: hidden;
  border-radius: 10px; padding: 4px 8px; cursor: pointer; margin: 1px 0 !important; }}
.ds-row:hover {{ background: var(--ds-surface); }}
.ds-row.active {{ background: var(--ds-blue-soft); }}
.ds-row.active .ds-title {{ color: var(--ds-blue-pressed); font-weight: 600; }}
/* A long question becomes the title, and a fixed-width sidebar has to clip it rather
   than let it run under the divider: `min-width: 0` on the flex child is what allows
   the ellipsis to engage at all. */
/* Only the outer flex item may take `width: 0` (that is what lets it shrink); the inner
   block must be full width or the title clips itself to nothing. */
.ds-row-text {{ display: block; width: 100%; min-width: 0; overflow: hidden; }}
.ds-cite {{ color: var(--ds-blue-pressed); background: var(--ds-blue-soft); border-radius: 999px;
  padding: 0 5px; margin-left: 2px; font-size: 11px; font-weight: 600; cursor: pointer;
  vertical-align: super; line-height: 1; }}
.ds-cite:hover {{ background: var(--ds-blue); color: #fff; }}
.ds-title {{ display: block; max-width: 100%; font-size: 13.5px; color: var(--ds-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.ds-meta {{ display: block; max-width: 100%; font-size: 11px; color: var(--ds-text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.ds-col {{ max-width: 720px; width: 100%; margin: 0 auto; padding: 0 20px; }}
/* The transcript is a column whose inherited gap was the remaining 16 px between
   messages. The composer row also carries `.ds-col`, so the rule must not force a
   direction on it. */
.ds-transcript {{ gap: 0 !important; }}
.q-drawer__content {{ padding: 6px 8px !important; }}
.ds-welcome {{ height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; }}
.ds-welcome h1 {{ font-size: 24px; font-weight: 700; margin: 0; }}
.ds-welcome p {{ color: var(--ds-text-2); margin: 0; font-size: 14px; }}
.ds-suggest {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 640px; }}
.ds-chip-suggest {{ border: 1px solid var(--ds-divider); border-radius: 999px; padding: 7px 14px;
  font-size: 13px; color: var(--ds-text-2); background: var(--ds-canvas); cursor: pointer; }}
.ds-chip-suggest:hover {{ background: var(--ds-surface); color: var(--ds-text); }}
.ds-msg {{ display: flex; margin: 8px 0; }}
.ds-msg.user {{ justify-content: flex-end; }}
.ds-user-bubble {{ background: var(--ds-blue-soft); color: var(--ds-text); border-radius: 18px 18px 4px 18px;
  padding: 10px 14px; max-width: 78%; white-space: pre-wrap; font-size: 15px; line-height: 1.6; }}
.ds-assistant {{ width: 100%; font-size: 15px; line-height: 1.65; color: var(--ds-text); }}
.ds-assistant p, .ds-assistant ul, .ds-assistant ol {{ margin: 0 !important; }}
.ds-assistant ul, .ds-assistant ol {{ padding-left: 20px; }}
.ds-assistant li {{ margin: 0; }}
.ds-assistant > :first-child {{ margin-top: 0 !important; }}
.ds-assistant > :last-child {{ margin-bottom: 0 !important; }}
.ds-assistant ul, .ds-assistant ol {{ padding-left: 22px; margin: 0 0 6px; }}
.ds-assistant li {{ margin: 2px 0; }}
.ds-assistant code {{ background: var(--ds-surface); border-radius: 4px; padding: 1px 5px;
  font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace; color: var(--ds-blue-pressed); }}
.ds-assistant pre {{ background: var(--ds-surface); border: 1px solid var(--ds-divider); border-radius: 8px; padding: 12px; overflow-x: auto; }}
.ds-assistant pre code {{ background: none; padding: 0; color: var(--ds-text); }}
.ds-badge {{ display: inline-block; border: 1px solid #f0d9a8; background: #fffaf0; color: #8a6d1f;
  border-radius: 999px; padding: 2px 10px; font-size: 12px; margin-top: 8px; }}
.ds-composer {{ position: sticky; bottom: 0; background: var(--ds-canvas); padding: 12px 0 18px; }}
.ds-input {{ background: var(--ds-surface) !important; border: 1px solid var(--ds-divider) !important;
  border-radius: 25px !important; padding: 8px 8px 8px 16px !important; box-shadow: none !important; }}
.ds-input .q-field__control {{ min-height: 46px; }}
.ds-send {{ background: var(--ds-blue) !important; color: #fff !important; border-radius: 50% !important;
  width: 40px; height: 40px; min-width: 40px; }}
.ds-send:disabled {{ background: #dfe1e7 !important; color: var(--ds-text-3) !important; }}
.ds-doc {{ font-size: 14px; font-weight: 600; }}
.ds-doc-meta {{ font-size: 11.5px; color: var(--ds-text-2); word-break: break-all; }}
.ds-doc-text {{ font: 12.5px/1.7 ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; color: #33353b; }}
.ds-doc-text mark {{ background: var(--ds-blue-soft); color: var(--ds-blue-pressed); border-radius: 3px; padding: 0 2px; }}
.ds-foot {{ font-size: 11px; color: var(--ds-text-3); }}
"""


SUGGESTIONS = [
    "What state does a Vault server start in?",
    "What address does the dev server listen on?",
    "What happens to leases when a token is revoked?",
    "What does sealing a Vault achieve during an incident?",
]


def html(content: str) -> ui.html:
    """A `ui.html` that does not need a `sanitize` argument at every call site.

    Everything this module interpolates is escaped by `_escape` or by
    `ChatEngine.citation_props` (which escapes the chunk and wraps the cited span in
    `<mark>`), so re-sanitising would only strip the highlight. One rule, one place.
    """
    return ui.html(content, sanitize=False)


def _store() -> history_mod.ConversationStore:
    """The process history, built once and shared by every browser tab."""
    return demo.get_history(os.environ.get(HISTORY_ENV, DEFAULT_HISTORY))


class Screen:
    def __init__(self) -> None:
        self.engine = demo.get_engine()
        self.store = _store()
        self.conversation_id: Optional[str] = None
        self.selected: set = set()
        self.manage = False
        self.busy = False
        # marker -> citation payload for the conversation on screen. Rebuilt on open and
        # extended on every answer, so an inline superscript can be resolved without
        # re-reading the transcript.
        self.citation_index: Dict[str, Dict[str, Any]] = {}
        self._build()

    # ---- layout ----------------------------------------------------------
    def _build(self) -> None:
        ui.add_css(CSS)

        with ui.left_drawer(value=True, bordered=False).props("width=280").classes("q-pa-sm"):
            with ui.row().classes("ds-brand w-full items-center justify-between no-wrap"):
                with ui.row().classes("items-center no-wrap").style("gap: 8px"):
                    html(WHALE)
                    html('<div class="ds-wordmark">Doc<span>QA</span></div>')
                self.manage_button = (
                    ui.button(icon="checklist", on_click=self._toggle_manage)
                    .props("flat round dense size=sm color=grey-7")
                    .tooltip("Select conversations to delete")
                )

            ui.button("＋  New chat", on_click=self._new_conversation).props("flat no-caps").classes("ds-new")

            # Only exists while selecting: the default sidebar is brand, new chat, list.
            self.manage_bar = ui.row().classes("w-full items-center justify-between ds-manage")
            with self.manage_bar:
                ui.checkbox("Select all", on_change=self._toggle_all).props("dense size=sm").classes("ds-foot")
                self.delete_button = ui.button("Delete", on_click=self._delete_selected).props(
                    "flat dense no-caps size=sm color=negative"
                )
            self.manage_bar.set_visibility(False)

            self.list_container = ui.column().classes("w-full gap-0")

        with ui.column().classes("w-full h-screen no-wrap gap-0 relative"):
            with ui.row().classes("w-full items-center justify-between q-px-md q-py-sm").style(
                f"border-bottom: 1px solid {DIVIDER}"
            ):
                self.title_label = ui.label("New chat").classes("text-[15px] font-semibold")
                with ui.row().classes("gap-1 items-center"):
                    ui.button(icon="tune", on_click=self._show_info).props("flat round dense color=grey-7")
                    ui.button(icon="edit_note", on_click=self._rename).props("flat round dense color=grey-7")

            # The scroll container must be the parent of both the welcome screen and the
            # transcript, or the reader ends up with a dead scrollbar beside a column that
            # grows past the viewport.
            with ui.column().classes("w-full flex-1 overflow-y-auto").style("min-height: 0") as self.body:
                self.welcome = ui.column().classes("ds-welcome w-full h-full")
                self.transcript = ui.column().classes("ds-col ds-transcript w-full")

            with ui.column().classes("w-full"):
                with ui.row().classes("ds-col items-end gap-2 ds-composer"):
                    self.question = (
                        ui.textarea(placeholder="Message DocQA…")
                        .props("borderless autogrow")
                        .classes("ds-input flex-1")
                    )
                    self.ask_button = ui.button(icon="arrow_upward", on_click=self._ask).props(
                        "unelevated round"
                    ).classes("ds-send")

        with ui.right_drawer(value=False, bordered=False).props("width=420").classes("q-pa-md") as self.drawer:
            self.drawer_title = html("").classes("ds-doc")
            self.drawer_meta = ui.label("").classes("ds-doc-meta q-mt-xs")
            self.drawer_body = html("").classes("ds-doc-text q-mt-md")

        # Inline superscripts are plain DOM inside one HTML element, so a delegated
        # listener plus NiceGUI's event bus is what lets them call back into Python
        # without a component per marker.
        ui.on("open_citation", lambda event: self._open_citation_marker(str(event.args.get("marker"))))
        ui.add_body_html(
            """
            <script>
            document.addEventListener('click', (event) => {
              const node = event.target.closest('.ds-cite');
              if (node && node.dataset.marker) {
                emitEvent('open_citation', {marker: node.dataset.marker});
              }
            });
            </script>
            """
        )
        self.question.on("keydown.enter", self._ask)
        self._render_welcome()
        self._refresh_list()
        self._open_latest_or_create()

    def _render_welcome(self) -> None:
        self.welcome.clear()
        with self.welcome:
            html(WHALE.replace('width="26" height="26"', 'width="44" height="44"'))
            html("<h1>Ask the Vault documentation</h1>")
            html("<p>Every claim comes back with a citation you can open.</p>")
            with ui.row().classes("ds-suggest q-mt-md"):
                for suggestion in SUGGESTIONS:
                    html(
                        f'<div class="ds-chip-suggest" data-q="{suggestion}">{suggestion}</div>'
                    ).on("click", lambda _event, text=suggestion: self._use_suggestion(text))

    def _use_suggestion(self, text: str) -> None:
        self.question.value = text
        self._ask()

    # ---- sidebar ---------------------------------------------------------
    def _toggle_manage(self) -> None:
        self.manage = not self.manage
        if not self.manage:
            self.selected.clear()
        self.manage_bar.set_visibility(self.manage)
        self.manage_button.props(f"color={'primary' if self.manage else 'grey-7'}")
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list_container.clear()
        rows = self.store.list(limit=100)
        groups = _group_by_day(rows)
        with self.list_container:
            for label, items in groups:
                html(f'<div class="ds-group">{label}</div>')
                for row in items:
                    self._row(row)
        self.delete_button.text = f"Delete ({len(self.selected)})" if self.selected else "Delete"

    def _row(self, row: Dict[str, Any]) -> None:
        active = " active" if row["id"] == self.conversation_id else ""
        title = _escape(_display_title(row.get("title")))
        turns = int(row["turns"])
        # The text is one HTML block rather than two labels: a label is a block element
        # with its own min-width, which is what let a long question overflow the sidebar
        # instead of ellipsing. `.ds-row-text` carries `min-width: 0`, the property that
        # actually permits the clip.
        with ui.element("div").classes("ds-row" + active):
            if self.manage:
                ui.checkbox(value=row["id"] in self.selected).props("dense").on(
                    "update:model-value",
                    lambda event, conversation=row["id"]: self._toggle(conversation, bool(event.args)),
                )
            html(
                f'<div class="ds-row-text" data-conversation="{row["id"]}">'
                f'<span class="ds-title">{title}</span>'
                f'<span class="ds-meta">{turns} message(s)</span>'
                "</div>"
            ).style("flex: 1 1 auto; width: 0; min-width: 0; overflow: hidden").on(
                "click", lambda _event, conversation=row["id"]: self._open(conversation)
            )
            ui.button(
                icon="more_horiz", on_click=lambda conversation=row["id"]: self._row_menu(conversation)
            ).props("flat round dense size=sm color=grey-6").classes("ds-row-menu")

    def _toggle(self, conversation_id: str, checked: bool) -> None:
        if checked:
            self.selected.add(conversation_id)
        else:
            self.selected.discard(conversation_id)
        self.delete_button.text = f"Delete ({len(self.selected)})" if self.selected else "Delete"

    def _toggle_all(self, event) -> None:
        """Select-all lives in the manage bar, which only exists while selecting."""
        if getattr(event, "value", False):
            self.selected = {row["id"] for row in self.store.list(limit=200)}
        else:
            self.selected.clear()
        self._refresh_list()

    def _row_menu(self, conversation_id: str) -> None:
        """Rename or delete one conversation.

        A `ui.menu()` built inside a click handler has no anchor and never opens unless
        it is told to, which is exactly the sort of control that looks present and does
        nothing. A dialog has no such trap and reads better on a projector anyway.
        """
        record = self.store.get(conversation_id) or {}
        with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
            ui.label(_display_title(record.get("title"))).classes("text-sm font-semibold")
            with ui.column().classes("w-full gap-1 q-mt-sm"):
                ui.button(
                    "Rename",
                    on_click=lambda: (dialog.close(), self._rename(conversation_id)),
                ).props("flat no-caps align=left").classes("w-full")
                ui.button(
                    "Delete",
                    on_click=lambda: (dialog.close(), self._delete([conversation_id])),
                ).props("flat no-caps align=left color=negative").classes("w-full")
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps color=grey-7").classes("w-full")
        dialog.open()

    def _delete_selected(self) -> None:
        if not self.selected:
            return
        ids = sorted(self.selected)
        with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
            ui.label(f"Delete {len(ids)} conversation(s)? This cannot be undone.")
            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Delete", on_click=lambda: (dialog.close(), self._delete(ids))).props(
                    "unelevated no-caps color=negative"
                )
        dialog.open()

    def _rename(self, conversation_id: Optional[str] = None) -> None:
        target = conversation_id or self.conversation_id
        if not target:
            return
        current = (self.store.get(target) or {}).get("title", "")
        with ui.dialog() as dialog, ui.card().classes("w-80 q-pa-md"):
            field = ui.input("Title", value=current).classes("w-full")
            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

                def apply():
                    title = (field.value or "").strip()
                    if title:
                        self.store.rename(target, title)
                        if target == self.conversation_id:
                            self.title_label.text = title
                        self._refresh_list()
                    dialog.close()

                ui.button("Save", on_click=apply).props("unelevated no-caps")
        dialog.open()

    # ---- conversations ---------------------------------------------------
    def _open_latest_or_create(self) -> None:
        rows = self.store.list(limit=1)
        if rows:
            self._open(rows[0]["id"])
        else:
            self._new_conversation()

    def _new_conversation(self) -> None:
        self.conversation_id = self.store.create()
        self.selected.discard(self.conversation_id)
        self.title_label.text = "New chat"
        self.transcript.clear()
        self.welcome.set_visibility(True)
        self._refresh_list()
        self.question.run_method("focus")

    def _open(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        record = self.store.get(conversation_id) or {}
        self.title_label.text = _display_title(record.get("title"))
        self.transcript.clear()
        self.citation_index = {}
        turns = self.store.messages(conversation_id)
        self.welcome.set_visibility(not turns)
        with self.transcript:
            for turn in turns:
                if turn["role"] == "user":
                    self._bubble_user(turn["content"])
                else:
                    self._bubble_assistant(turn["content"], turn["payload"])
        self._refresh_list()

    def _delete(self, ids: List[str]) -> None:
        deleted = [conversation_id for conversation_id in ids if self.store.delete(conversation_id)]
        for conversation_id in deleted:
            self.selected.discard(conversation_id)
        if self.conversation_id in deleted:
            self.conversation_id = None
        ui.notify(f"Deleted {len(deleted)} conversation(s)", type="info")
        self._refresh_list()
        if self.conversation_id is None:
            self._open_latest_or_create()

    # ---- transcript ------------------------------------------------------
    def _bubble_user(self, text: str) -> None:
        with self.transcript:
            with ui.row().classes("ds-msg user w-full"):
                html(f'<div class="ds-user-bubble">{_escape(text)}</div>')

    def _bubble_assistant(self, markdown: str, payload: Optional[Dict[str, Any]]) -> None:
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
        self._open_citation(citation)

    # ---- asking ----------------------------------------------------------
    async def _ask(self) -> None:
        question = (self.question.value or "").strip()
        if not question or self.busy:
            return
        self.busy = True
        self.ask_button.disable()
        self.question.value = ""
        self.welcome.set_visibility(False)
        if not self.conversation_id:
            self._new_conversation()
            self.welcome.set_visibility(False)
        self.store.append(self.conversation_id, "user", question)
        self._bubble_user(question)
        with self.transcript:
            thinking = ui.label("Searching the documentation…").classes("ds-foot")
        try:
            with ANSWER_LOCK:
                response = await run.io_bound(self.engine.answer, question)
        except Exception as error:  # noqa: BLE001 - the reader must see the reason
            thinking.delete()
            message = f"**The answer did not arrive.** `{type(error).__name__}: {error}`"
            self.store.append(self.conversation_id, "assistant", message)
            self._bubble_assistant(message, None)
            ui.notify("Answer failed — the reason is in the transcript", type="negative")
            self.busy = False
            self.ask_button.enable()
            return

        thinking.delete()
        rendered = demo.render_answer(response)
        payload = {
            "abstained": response["abstained"],
            "abstain_reason": response["abstain_reason"],
            "claims": [
                {"marker": claim["marker"], "citation": self.engine.citation_payload(claim)}
                for claim in response["claims"]
                if claim["verified"]
            ],
        }
        self.store.append(self.conversation_id, "assistant", rendered, payload=payload)
        record = self.store.get(self.conversation_id) or {}
        self.title_label.text = _display_title(record.get("title"))
        self._bubble_assistant(rendered, payload)
        self._refresh_list()
        self.busy = False
        self.ask_button.enable()

    # ---- source drawer ---------------------------------------------------
    def _open_citation(self, citation: Dict[str, Any]) -> None:
        try:
            props = self.engine.citation_props(citation)
        except (KeyError, ValueError) as error:
            ui.notify(f"Citation could not be opened: {error}", type="negative")
            return
        self.drawer_title.content = (
            f'<div class="ds-doc">{_escape(props.get("marker", ""))} · '
            f'{_escape(props.get("doc_title", ""))}</div>'
        )
        bits = [value for value in (props.get("heading_path"), props.get("url")) if value]
        self.drawer_meta.text = " · ".join(bits)
        self.drawer_body.content = props.get("chunk_html") or _escape(props.get("span_text", ""))
        self.drawer.value = True

    def _show_info(self) -> None:
        engine = self.engine
        with ui.dialog() as dialog, ui.card().classes("q-pa-md"):
            ui.label("What is answering").classes("text-sm font-semibold")
            ui.markdown(
                f"- configuration `{engine.config_name}`\n"
                f"- snapshot `{engine.snapshot_id}`, {engine.chunk_count} chunks\n"
                f"- retrieval `{engine.cfg['retrieval.mode']}`, k={engine.k}\n"
                f"- generator `{getattr(engine.generator, 'model_id', '?')}`"
            ).classes("text-[13px]")
            ui.button("Close", on_click=dialog.close).props("flat no-caps")
        dialog.open()


CITATION = re.compile(r"\[(\d+)\]")


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


def _display_title(title: Optional[str]) -> str:
    """The store calls an unnamed conversation "Untitled conversation"; a chat product
    says "New chat". One mapping, applied wherever a title is shown."""
    text = (title or "").strip()
    if not text or text == "Untitled conversation":
        return "New chat"
    return text


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _group_by_day(rows: List[Dict[str, Any]]):
    """DeepSeek groups history by recency; a flat list buries yesterday."""
    import datetime as dt

    today = dt.date.today()
    buckets: List[tuple] = [("Today", []), ("Yesterday", []), ("Previous 7 days", []), ("Earlier", [])]
    for row in rows:
        try:
            stamp = dt.date.fromisoformat(str(row.get("updated_at", ""))[:10])
        except ValueError:
            buckets[-1][1].append(row)
            continue
        age = (today - stamp).days
        index = 0 if age <= 0 else 1 if age == 1 else 2 if age <= 7 else 3
        buckets[index][1].append(row)
    return [(label, items) for label, items in buckets if items]


def serve(config_path: str, host: str = "127.0.0.1", port: int = 8200) -> int:
    os.environ[demo.CONFIG_ENV] = os.path.abspath(config_path)
    engine = demo.install_engine(demo.ChatEngine.from_config(config_path))
    print(
        f"demo(nice): configuration {engine.config_name!r} "
        f"({engine.chunk_count} chunks, {engine.index_backend} index) "
        f"loaded in {engine.build_seconds:.1f}s"
    )
    print(f"demo(nice): history at {_store().path}")
    print(f"demo(nice): serving http://{host}:{port}")

    @ui.page("/")
    def index() -> None:
        try:
            Screen()
        except Exception as error:  # noqa: BLE001 - a 500 with no message is useless
            ui.label("The demo failed to start").classes("text-lg")
            ui.markdown(f"`{type(error).__name__}: {error}`")
            ui.label("The traceback is in the terminal that started it.")

    ui.run(host=host, port=int(port), title="DocQA · grounded documentation answers", dark=False,
           show=False, reload=False, favicon="🐳")
    return 0
