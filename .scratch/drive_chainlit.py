"""Drive the Chainlit 2.3.0 surface headlessly: recording emitter, real handlers.

Ticket 16 has to show that a citation marker actually opens a source panel, and a
browser is not available on the demo machine for verification. This script replaces
the websocket with a recording emitter and calls the registered handlers directly, so
the exact payload a click carries and the exact props the panel receives can be read
back from a terminal.

    python .scratch/drive_chainlit.py            # fixture configuration, offline
    RAGQA_DEMO_CONFIG=configs/real_llm.yaml python .scratch/drive_chainlit.py

It asserts nothing; it prints. What it printed for the fixture path is quoted in
`notes/demo-script.md`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ.setdefault("RAGQA_DEMO_CONFIG", "configs/smoke.yaml")
sys.path.insert(0, os.path.abspath("."))

import chainlit as cl
from chainlit.context import ChainlitContext, context_var, local_steps
from chainlit.emitter import BaseChainlitEmitter
from chainlit.session import HTTPSession

from ragqa import chainlit_app as app

SENT = []


class RecordingEmitter(BaseChainlitEmitter):
    """Same shape as the real emitter, recording instead of emitting."""

    async def send_step(self, step_dict):
        SENT.append(("step", step_dict))

    async def send_element(self, element_dict):
        SENT.append(("element", element_dict))

    async def emit(self, event, data=None, **kwargs):
        SENT.append((event, data))


async def main() -> None:
    local_steps.set([])
    session = HTTPSession(
        id="drive-session", client_type="webapp", thread_id="drive-thread"
    )
    context_var.set(ChainlitContext(session, emitter=RecordingEmitter(session)))

    await app.on_chat_start()
    opening = [p for kind, p in SENT if kind == "step"][-1]
    print("== on_chat_start ==")
    print(opening["output"])

    question = "Which setting controls the number of threads used for background merges?"
    SENT.clear()
    await app.on_message(cl.Message(content=question, author="User"))

    answer = [p for kind, p in SENT if kind == "step" and p.get("output")][-1]
    actions = [p for kind, p in SENT if kind == "action"]
    print("\n== on_message ==")
    print(answer["output"])
    print("-- actions attached to the answer --")
    for action in actions:
        print(f"{action['label']} -> {action['name']} {json.dumps(action['payload'])}")

    if not actions:
        print("\nno citation action: nothing to click")
        return

    click = actions[0]
    SENT.clear()
    await app.open_citation(
        cl.Action(name=click["name"], payload=click["payload"], label=click["label"])
    )
    panel = [p for kind, p in SENT if kind == "step"][-1]
    element = [p for kind, p in SENT if kind == "element"][-1]
    props = element["props"]
    print("\n== on_action('open_citation') ==")
    print(panel["output"])
    print(f"element: {element['name']} display={element['display']}")
    print("props:", sorted(props))
    print("doc_title:", props["doc_title"])
    print("heading_path:", props["heading_path"])
    print("url:", props["url"])
    marked = props["chunk_html"].split("<mark>")[1].split("</mark>")[0]
    print("marked span:", marked[:160].replace("\n", " "))


asyncio.run(main())
