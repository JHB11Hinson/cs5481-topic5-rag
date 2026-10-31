"""A DeepSeek-shaped RAG screen in NiceGUI: sidebar, transcript, source drawer.

Why a third surface exists. Chainlit gives a chat stream and nothing else (its sidebar
needs a data layer, its elements cannot call back). The hand-rolled page proved the layout
but asked the reader to look at Markdown asterisks and a JSON blob, because it rendered
answers as plain text. NiceGUI is a real component framework — Quasar under the hood — so
the same layout gets proper Markdown, real scrolling, and reactive updates without a build
step or a Node toolchain in the submission.

    python -m ragqa serve --config configs/... --backend nice --port 8200

Design rules taken from the failed demo, not from taste:

- **Nothing on screen that is machinery.** No chunk ids, no scores, no latency line, no
  error classes. They live in `payload` and appear only in the source drawer.
- **A code block never reaches a reader.** `demo._prose_excerpt` strips fences and JSON
  before anything is displayed; an abstention says one sentence and names the closest page.
- **One answer at a time.** The index is single-tenant (embedded Qdrant, one GPU), so the
  ask handler holds a lock and the button disables itself while a question is in flight.
"""

from __future__ import annotations

import html
import os
import threading
from typing import Any, Dict, List, Optional

from nicegui import run, ui

from . import demo, history as history_mod

ANSWER_LOCK = threading.Lock()
HISTORY_ENV = "RAGQA_DEMO_HISTORY"
DEFAULT_HISTORY = "data/demo/history.sqlite"


def _store() -> history_mod.ConversationStore:
    return demo.get_history(os.environ.get(HISTORY_ENV, DEFAULT_HISTORY))


class Screen:
    """One page: the state the sidebar, transcript and drawer share."""

    def __init__(self) -> None:
        self.engine = demo.get_engine()
        self.store = _store()
        self.conversation_id: Optional[str] = None
        self.selected: set = set()
        self.busy = False

        self._build()

    # ---- layout ----------------------------------------------------------
    def _build(self) -> None:
        ui.dark_mode().enable()
        ui.add_css(
            """
            body { background: #0f1115; }
            .q-drawer { background: #14161c !important; border-right: 1px solid #23262f; }
            .bubble { border-radius: 14px; padding: 12px 14px; max-width: 860px; }
            .bubble.user { background: #23304a; margin-left: auto; }
            .bubble.assistant { background: #171a21; border: 1px solid #23262f; }
            .bubble p:first-child { margin-top: 0; }
            .bubble p:last-child { margin-bottom: 0; }
            .row-conv { border-radius: 8px; padding: 4px 6px; cursor: pointer; }
            .row-conv:hover { background: #1b1f27; }
            .row-conv.active { background: #223052; }
            .conv-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .conv-meta { font-size: 11px; color: #8b93a3; }
            .drawer-text { font: 12px/1.6 ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; color: #cfd6e4; }
            .drawer-text mark { background: #3a3418; color: #ffe9a3; border-radius: 3px; }
            """
        )

        with ui.left_drawer(value=True).props("width=290 bordered").classes("q-pa-sm"):
            ui.button("＋  New chat", on_click=self._new_conversation).props("unelevated").classes("w-full")
            with ui.row().classes("w-full items-center justify-between q-mt-sm"):
                ui.checkbox("Select all", on_change=self._toggle_all).props("dense").classes("text-xs")
                self.delete_button = ui.button(
                    "Delete selected", on_click=self._delete_selected
                ).props("flat dense color=negative").classes("text-xs")
                self.delete_button.disable()
            self.list_container = ui.column().classes("w-full gap-1 q-mt-sm")
            self.config_line = ui.label("").classes("text-[11px] text-gray-500 q-mt-md")

        with ui.column().classes("w-full h-screen no-wrap gap-0"):
            with ui.row().classes("w-full items-center justify-between q-px-md q-py-sm border-b"):
                with ui.column().classes("gap-0"):
                    self.title_label = ui.label("New conversation").classes("text-base font-medium")
                    self.meta_label = ui.label("").classes("text-[11px] text-gray-500")
                with ui.row().classes("gap-2"):
                    self.info_button = ui.button(icon="info_outline", on_click=self._show_info).props("flat round dense")
                    ui.button("Rename", on_click=self._rename).props("flat dense")

            self.transcript = ui.column().classes("w-full flex-1 overflow-y-auto q-pa-md gap-3")
            with ui.row().classes("w-full items-end gap-2 q-pa-md border-t"):
                self.question = (
                    ui.textarea(placeholder="Ask a question about the documentation…")
                    .props("outlined autogrow dense")
                    .classes("flex-1")
                )
                self.ask_button = ui.button("Ask", on_click=self._ask).props("unelevated")

        with ui.right_drawer(value=False).props("width=420 bordered").classes("q-pa-sm") as self.drawer:
            self.drawer_title = ui.label("Source").classes("text-sm font-medium")
            self.drawer_meta = ui.label("").classes("text-[11px] text-gray-500")
            # `sanitize=False` because the chunk HTML is already escaped server-side in
            # `ChatEngine.citation_props`; letting NiceGUI strip it again would remove the
            # `<mark>` that makes the cited span visible, which is the whole point of the
            # panel. One escaping rule, in one place.
            self.drawer_body = ui.html("", sanitize=False).classes("drawer-text q-mt-sm")

        self.question.on("keydown.enter", self._ask)
        self._refresh_config()
        self._refresh_list()
        self._open_latest_or_create()

    # ---- data ------------------------------------------------------------
    def _refresh_config(self) -> None:
        engine = self.engine
        self.config_line.text = (
            f"{engine.config_name} · {engine.chunk_count} chunks · "
            f"{engine.cfg['retrieval.mode']} k={engine.k}"
        )

    def _refresh_list(self) -> None:
        self.list_container.clear()
        current = self.conversation_id
        with self.list_container:
            for row in self.store.list(limit=100):
                active = " row-conv active" if row["id"] == current else " row-conv"
                with ui.row().classes("w-full items-center gap-2" + active):
                    box = ui.checkbox(value=row["id"] in self.selected).props("dense")
                    box.on(
                        "update:model-value",
                        lambda event, conversation=row["id"]: self._toggle(conversation, bool(event.args)),
                    )
                    with ui.column().classes("gap-0 flex-1").on("click", lambda conversation=row["id"]: self._open(conversation)):
                        ui.label(row["title"] or "Untitled conversation").classes("conv-title")
                        ui.label(f"{row['turns']} turn(s) · {row['updated_at'][11:16]} UTC").classes("conv-meta")
                    ui.button(icon="close", on_click=lambda conversation=row["id"]: self._delete([conversation])).props(
                        "flat round dense size=sm color=grey"
                    )
        self.delete_button.text = f"Delete ({len(self.selected)})" if self.selected else "Delete selected"
        if self.selected:
            self.delete_button.enable()
        else:
            self.delete_button.disable()

    def _open_latest_or_create(self) -> None:
        rows = self.store.list(limit=1)
        if rows:
            self._open(rows[0]["id"])
        else:
            self._new_conversation()

    # ---- sidebar actions -------------------------------------------------
    def _toggle(self, conversation_id: str, checked: bool) -> None:
        if checked:
            self.selected.add(conversation_id)
        else:
            self.selected.discard(conversation_id)
        self._refresh_list()

    def _toggle_all(self, event) -> None:
        self.selected = {row["id"] for row in self.store.list(limit=100)} if event.value else set()
        self._refresh_list()

    def _new_conversation(self) -> None:
        self.conversation_id = self.store.create()
        self.selected.discard(self.conversation_id)
        self.title_label.text = "New conversation"
        self.meta_label.text = self.conversation_id
        self.transcript.clear()
        self._refresh_list()
        self.question.run_method("focus")

    def _open(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        record = self.store.get(conversation_id) or {}
        self.title_label.text = record.get("title") or "Untitled conversation"
        self.meta_label.text = conversation_id
        self.transcript.clear()
        with self.transcript:
            for turn in self.store.messages(conversation_id):
                if turn["role"] == "user":
                    self._bubble_user(turn["content"])
                else:
                    self._bubble_assistant(turn["content"], turn["payload"])
        self._refresh_list()

    def _delete(self, ids: List[str]) -> None:
        if not ids:
            return
        deleted = [conversation_id for conversation_id in ids if self.store.delete(conversation_id)]
        for conversation_id in deleted:
            self.selected.discard(conversation_id)
        if self.conversation_id in deleted:
            self.conversation_id = None
        ui.notify(f"Deleted {len(deleted)} conversation(s)", type="info")
        self._refresh_list()
        if self.conversation_id is None:
            self._open_latest_or_create()

    def _delete_selected(self) -> None:
        if not self.selected:
            return
        ids = sorted(self.selected)
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Delete {len(ids)} conversation(s)? This cannot be undone.")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=lambda: (dialog.close(), self._delete(ids))).props("unelevated color=negative")
        dialog.open()

    def _rename(self) -> None:
        if not self.conversation_id:
            return
        with ui.dialog() as dialog, ui.card().classes("w-80"):
            field = ui.input("Title", value=self.title_label.text).classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def apply():
                    title = (field.value or "").strip()
                    if title:
                        self.store.rename(self.conversation_id, title)
                        self.title_label.text = title
                        self._refresh_list()
                    dialog.close()

                ui.button("Save", on_click=apply).props("unelevated")
        dialog.open()

    def _show_info(self) -> None:
        engine = self.engine
        with ui.dialog() as dialog, ui.card():
            ui.label("What is answering").classes("text-sm font-medium")
            ui.markdown(
                f"- configuration `{engine.config_name}`\n"
                f"- snapshot `{engine.snapshot_id}`, {engine.chunk_count} chunks\n"
                f"- retrieval `{engine.cfg['retrieval.mode']}`, k={engine.k}\n"
                f"- generator `{getattr(engine.generator, 'model_id', '?')}`\n"
                f"- loaded in {engine.build_seconds:.1f}s"
            )
            ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()

    # ---- bubbles ---------------------------------------------------------
    def _bubble_user(self, text: str) -> None:
        with self.transcript:
            with ui.row().classes("w-full justify-end"):
                ui.label(text).classes("bubble user whitespace-pre-wrap")

    def _bubble_assistant(self, markdown: str, payload: Optional[Dict[str, Any]]) -> None:
        with self.transcript:
            with ui.column().classes("bubble assistant gap-2"):
                ui.markdown(markdown or "")
                chips = (payload or {}).get("claims") or []
                abstained = bool((payload or {}).get("abstained"))
                if chips or abstained:
                    with ui.row().classes("gap-1 items-center"):
                        for claim in chips:
                            ui.button(
                                claim["marker"],
                                on_click=lambda citation=claim["citation"]: self._open_citation(citation),
                            ).props("flat dense rounded size=sm color=primary").classes("text-xs")
                        if abstained:
                            ui.badge("abstained", color="amber").props("outline").classes("text-xs")
        self._scroll_to_end()

    def _scroll_to_end(self) -> None:
        self.transcript.run_method(
            "scrollTo", {"top": 100000, "behavior": "smooth"}
        )

    # ---- asking ----------------------------------------------------------
    async def _ask(self) -> None:
        question = (self.question.value or "").strip()
        if not question or self.busy:
            return
        self.busy = True
        self.ask_button.disable()
        self.question.value = ""
        if not self.conversation_id:
            self._new_conversation()
        self.store.append(self.conversation_id, "user", question)
        self._bubble_user(question)
        thinking = None
        with self.transcript:
            thinking = ui.label("Searching the documentation…").classes("text-xs text-gray-500")
        try:
            with ANSWER_LOCK:
                response = await run.io_bound(self.engine.answer, question)
        except Exception as error:  # noqa: BLE001 - the reader must see the reason
            thinking.delete()
            message = f"**The answer did not arrive.** `{type(error).__name__}: {error}`"
            self.store.append(self.conversation_id, "assistant", message)
            self._bubble_assistant(message, None)
            ui.notify("Answer failed — see the transcript", type="negative")
            self.busy = False
            self.ask_button.enable()
            return

        thinking.delete()
        rendered = demo.render_answer(response)
        payload = {
            "abstained": response["abstained"],
            "abstain_reason": response["abstain_reason"],
            "claims": [
                {
                    "marker": claim["marker"],
                    "citation": self.engine.citation_payload(claim),
                }
                for claim in response["claims"]
                if claim["verified"]
            ],
        }
        self.store.append(self.conversation_id, "assistant", rendered, payload=payload)
        record = self.store.get(self.conversation_id) or {}
        self.title_label.text = record.get("title") or "New conversation"
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
        self.drawer_title.text = f"Source {props.get('marker', '')} — {props.get('doc_title', '')}"
        bits = [value for value in (props.get("heading_path"), props.get("url")) if value]
        self.drawer_meta.text = " · ".join(bits)
        self.drawer_body.content = props.get("chunk_html") or html.escape(props.get("span_text", ""))
        self.drawer.value = True


def serve(config_path: str, host: str = "127.0.0.1", port: int = 8200) -> int:
    """Load the pipeline once, then serve one page. Blocks like any NiceGUI app."""
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
            ui.label("The traceback is in the server log next to the terminal that started it.")

    ui.run(host=host, port=int(port), title="Grounded documentation QA", dark=True, show=False, reload=False, favicon="🔎")
    return 0
