"""Drive the history-aware Chainlit surface headlessly.

The old driver inspected the message a handler *sent*; the new surface sends a
placeholder and then fills it in with `.update()`, so this one records both. It walks the
whole conversation lifecycle against the fixture configuration — no network, no GPU — and
prints the store afterwards, which is the evidence that a chat survives a tab:

    on_chat_start → /help → question → /history → /new → question → /open <id> → /title

    python .scratch/drive_history.py
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("RAGQA_DEMO_CONFIG", "configs/smoke.yaml")
os.environ.setdefault("RAGQA_DEMO_HISTORY", "data/demo/history-driver2.sqlite")
sys.path.insert(0, os.path.abspath("."))

import chainlit as cl  # noqa: E402
from chainlit.context import ChainlitContext, context_var, local_steps  # noqa: E402
from chainlit.emitter import BaseChainlitEmitter  # noqa: E402
from chainlit.session import HTTPSession  # noqa: E402

from ragqa import chainlit_app as app  # noqa: E402
from ragqa import demo  # noqa: E402

SENT: list = []


class RecordingEmitter(BaseChainlitEmitter):
    def send(self, *args, **kwargs):  # noqa: D401 - Chainlit hook
        return None


def record(message) -> None:
    SENT.append(
        {
            "content": message.content,
            "actions": [action.label for action in (message.actions or [])],
            "elements": [getattr(element, "name", "?") for element in (message.elements or [])],
        }
    )


async def main() -> None:
    original_send = cl.Message.send
    original_update = cl.Message.update
    original_stream = cl.Message.stream_token

    async def send(self, *args, **kwargs):
        record(self)
        return self

    async def update(self, *args, **kwargs):
        record(self)
        return self

    async def stream_token(self, *args, **kwargs):
        return False

    cl.Message.send = send
    cl.Message.update = update
    cl.Message.stream_token = stream_token
    cl.Action.send = send if hasattr(cl.Action, "send") else None

    session = HTTPSession(
        id="driver-session",
        client_type="webapp",
        user_env={},
        user=None,
        http_referer=None,
    )
    context = ChainlitContext(session=session, emitter=RecordingEmitter(session))
    token = context_var.set(context)
    local_steps.set({})
    try:
        await app.on_chat_start()
        opening = SENT[-1]
        conversation = cl.user_session.get("conversation_id")
        print("start:", conversation, "| actions:", opening["actions"])

        await app.on_message(cl.Message(content="/help"))
        print("help:", SENT[-1]["content"].splitlines()[0])

        await app.on_message(cl.Message(content="What state does a Vault server start in?"))
        answer = SENT[-1]
        print("answer actions:", answer["actions"])
        print("answer first line:", answer["content"].splitlines()[0][:90])

        await app.on_message(cl.Message(content="/history"))
        print("history:")
        for line in SENT[-1]["content"].splitlines():
            if line.startswith("- "):
                print("   ", line)

        await app.on_message(cl.Message(content="/new second window"))
        second = cl.user_session.get("conversation_id")
        print("new conversation:", second)

        await app.on_message(cl.Message(content="/open " + conversation))
        print("replayed turns:", sum(1 for item in SENT[-6:] if item["content"]))
        print("replay carried actions:", any(item["actions"] for item in SENT[-6:]))

        await app.on_message(cl.Message(content="/title named on purpose"))
        store = demo.get_history()
        print("store now:")
        for row in store.list(limit=5):
            print(f"    {row['id']}  turns={row['turns']}  title={row['title']!r}")
    finally:
        context_var.reset(token)
        cl.Message.send = original_send
        cl.Message.update = original_update
        cl.Message.stream_token = original_stream


if __name__ == "__main__":
    asyncio.run(main())
