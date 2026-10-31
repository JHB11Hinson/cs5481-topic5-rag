"""The Chainlit surface: conversations with history, one clickable marker per claim.

This module is deliberately thin. Everything it shows comes from `ragqa.demo` (the
pipeline, built once per process, returning plain dicts) and `ragqa.history` (the
conversation store, a small SQLite file). Keeping it thin is what lets both be tested
outside a browser.

Three details of Chainlit 2.3.0 shaped the wiring:

- There is no `cl.on_action`; the decorator that registers a click handler is
  `cl.action_callback(name)`.
- A custom element becomes a panel the moment its renderer is fetched from
  `/public/elements/<name>.jsx` and evaluated in the browser, so the renderer lives in
  `public/elements/CitationCard.jsx` and receives the panel as `props`.
- `@cl.on_chat_resume` only fires with a Chainlit data layer, which this demo does not
  run. History is therefore explicit: every tab owns a conversation id, `/history` lists
  the store, and `/open <id>` attaches a tab to an existing conversation and replays it.

**The answers run in a worker thread** (`cl.make_async`), which is why every cache in the
pipeline had to become thread-safe, why a failure is now reported to the screen instead of
vanishing into the log, and why the engine is guarded by a lock: the GPU and the index are
single-tenant, so two tabs asking at once queue rather than collide.
"""

from __future__ import annotations

import os
import sys
import threading

import chainlit as cl

try:  # imported as part of the package, via `python -m ragqa serve`
    from . import demo
except ImportError:  # chainlit loads this file by path, outside the package
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ragqa import demo

ACTION_OPEN_CITATION = "open_citation"
ACTION_NEW_CONVERSATION = "new_conversation"
ACTION_HISTORY = "show_history"
CITATION_ELEMENT = "CitationCard"

# One answer at a time: the index is embedded Qdrant (single writer) and the card is
# shared with whatever else is running. Two tabs queue instead of fighting.
_ANSWER_LOCK = threading.Lock()

HISTORY_ENV = "RAGQA_DEMO_HISTORY"
DEFAULT_HISTORY = "data/demo/history.sqlite"

HELP = (
    "**Commands**\n"
    "- `/new [title]` — start a fresh conversation in this tab\n"
    "- `/history [n]` — list the last n conversations with their ids\n"
    "- `/open <id>` — attach this tab to a conversation and replay it\n"
    "- `/title <text>` — rename the current conversation\n"
    "- `/delete <id>` — delete a conversation\n"
    "- `/help` — this list\n\n"
    "Open a second browser tab for a second conversation; both share one history file, so "
    "`/open` moves between them."
)


def _store():
    return demo.get_history(os.environ.get(HISTORY_ENV, DEFAULT_HISTORY))


def _conversation_id() -> str:
    conversation_id = cl.user_session.get("conversation_id")
    if conversation_id and _store().exists(conversation_id):
        return conversation_id
    conversation_id = _store().create()
    cl.user_session.set("conversation_id", conversation_id)
    return conversation_id


def _actions_for(payload) -> list:
    """Rebuild the citation markers of a stored answer."""
    if not payload:
        return []
    return [
        cl.Action(
            name=ACTION_OPEN_CITATION,
            label=claim.get("marker", "[?]"),
            tooltip=claim.get("tooltip", ""),
            payload=claim.get("payload", {}),
        )
        for claim in payload.get("claims", [])
        if claim.get("marker")
    ]


def _answer_payload(response) -> dict:
    """What has to survive in the store for a replayed answer to stay clickable."""
    engine = demo.get_engine()
    return {
        "config_name": response["config_name"],
        "abstained": response["abstained"],
        "retrieval_ms": response["retrieval_ms"],
        "claims": [
            {
                "marker": claim["marker"],
                "verified": claim["verified"],
                "tooltip": f"{claim['doc_title']} > {claim['heading_path']}",
                "payload": engine.citation_payload(claim),
            }
            for claim in response["claims"]
            if claim["verified"]
        ],
    }


async def _replay(conversation_id: str) -> None:
    """Walk a stored conversation back onto the screen, markers included."""
    store = _store()
    record = store.get(conversation_id)
    if record is None:
        await cl.Message(content=f"No conversation `{conversation_id}`.").send()
        return
    turns = store.messages(conversation_id)
    await cl.Message(
        content=f"**Conversation `{record['id']}`** — {record['title']} "
        f"({record['turns']} turn(s), last used {record['updated_at']} UTC)"
    ).send()
    for turn in turns:
        if turn["role"] == "user":
            await cl.Message(content=turn["content"], author="you").send()
        else:
            await cl.Message(
                content=turn["content"], actions=_actions_for(turn["payload"])
            ).send()


async def _handle_command(text: str) -> None:
    store = _store()
    parts = text.strip().split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        await cl.Message(content=HELP).send()
        return

    if command == "/new":
        conversation_id = store.create(argument)
        cl.user_session.set("conversation_id", conversation_id)
        await cl.Message(
            content=f"Started conversation `{conversation_id}`. Ask anything."
        ).send()
        return

    if command == "/history":
        limit = int(argument) if argument.isdigit() else 8
        rows = store.list(limit=limit)
        if not rows:
            await cl.Message(content="No conversations yet — ask a question to make one.").send()
            return
        current = cl.user_session.get("conversation_id")
        lines = ["**Recent conversations** (newest first)", ""]
        for row in rows:
            mark = " ← this tab" if row["id"] == current else ""
            lines.append(
                f"- `{row['id']}` · {row['turns']} turn(s) · {row['updated_at']} · "
                f"{row['title']}{mark}"
            )
        lines += ["", "`/open <id>` to continue one of them."]
        await cl.Message(content="\n".join(lines)).send()
        return

    if command == "/open":
        if not argument:
            await cl.Message(content="Usage: `/open <id>` — ids come from `/history`.").send()
            return
        if not store.exists(argument):
            await cl.Message(content=f"No conversation `{argument}`.").send()
            return
        cl.user_session.set("conversation_id", argument)
        await _replay(argument)
        return

    if command == "/title":
        conversation_id = _conversation_id()
        if not argument:
            await cl.Message(content="Usage: `/title <text>`.").send()
            return
        store.rename(conversation_id, argument)
        await cl.Message(content=f"Renamed `{conversation_id}` to **{argument}**.").send()
        return

    if command == "/delete":
        if not argument:
            await cl.Message(content="Usage: `/delete <id>`.").send()
            return
        removed = store.delete(argument)
        if removed and cl.user_session.get("conversation_id") == argument:
            cl.user_session.set("conversation_id", store.create())
        await cl.Message(
            content=f"Deleted `{argument}`." if removed else f"No conversation `{argument}`."
        ).send()
        return

    await cl.Message(content=f"Unknown command `{command}`.\n\n{HELP}").send()


@cl.on_chat_start
async def on_chat_start() -> None:
    """State what is served, open a conversation, and offer the two useful buttons."""
    engine = demo.get_engine()
    conversation_id = _conversation_id()
    await cl.Message(
        content=(
            engine.describe()
            + f"\n\nConversation `{conversation_id}`. Ask a question, or use the buttons."
            + "\n\nTry: _What state does a Vault server start in, and what can it not do "
            "in that state?_"
        ),
        actions=[
            cl.Action(name=ACTION_NEW_CONVERSATION, label="New conversation", payload={}),
            cl.Action(name=ACTION_HISTORY, label="History", payload={}),
        ],
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = (message.content or "").strip()
    if not text:
        return
    if text.startswith("/"):
        await _handle_command(text)
        return

    store = _store()
    conversation_id = _conversation_id()
    store.append(conversation_id, "user", text)

    engine = demo.get_engine()
    thinking = cl.Message(content=f"_Retrieving and answering for `{conversation_id}`…_")
    await thinking.send()

    try:
        with _ANSWER_LOCK:
            response = await cl.make_async(engine.answer)(text)
    except Exception as exc:  # noqa: BLE001 - the screen must show what the log knows
        detail = f"{type(exc).__name__}: {exc}"
        store.append(
            conversation_id,
            "assistant",
            f"**The answer did not arrive.** `{detail}`\n\n"
            "The question is kept in this conversation; ask again to retry — the response "
            "cache makes a second attempt cheap.",
        )
        thinking.content = (
            f"**The answer did not arrive.** `{detail}`\n\n"
            "Nothing was lost: the question is stored in this conversation. Ask again to "
            "retry; a repeated request is cached and costs nothing."
        )
        await thinking.update()
        return

    rendered = demo.render_answer(response)
    store.append(conversation_id, "assistant", rendered, payload=_answer_payload(response))
    thinking.content = rendered
    thinking.actions = [
        cl.Action(
            name=ACTION_OPEN_CITATION,
            label=claim["marker"],
            tooltip=f"{claim['doc_title']} > {claim['heading_path']}",
            payload=engine.citation_payload(claim),
        )
        for claim in response["claims"]
        if claim["verified"]
    ]
    await thinking.update()


@cl.action_callback(ACTION_NEW_CONVERSATION)
async def new_conversation(action: cl.Action) -> None:
    store = _store()
    conversation_id = store.create()
    cl.user_session.set("conversation_id", conversation_id)
    await cl.Message(content=f"Started conversation `{conversation_id}`. Ask anything.").send()


@cl.action_callback(ACTION_HISTORY)
async def show_history(action: cl.Action) -> None:
    await _handle_command("/history")


@cl.action_callback(ACTION_OPEN_CITATION)
async def open_citation(action: cl.Action) -> None:
    """Marker clicked: build the source panel from the index and send it."""
    engine = demo.get_engine()
    try:
        props = engine.citation_props(action.payload)
    except (KeyError, ValueError) as exc:
        await cl.Message(content=f"**Citation could not be opened.** {exc}").send()
        return

    line = f"**Source {props['marker']}** - {props['doc_title']}"
    if props["heading_path"]:
        line += f" > {props['heading_path']}"
    if props["url"]:
        line += f" - {props['url']}"
    await cl.Message(
        content=line + "\n\nThe cited span is highlighted in the panel.",
        elements=[cl.CustomElement(name=CITATION_ELEMENT, props=props, display="side")],
    ).send()
