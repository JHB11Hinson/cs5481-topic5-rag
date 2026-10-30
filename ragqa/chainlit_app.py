"""The Chainlit surface: one message per answer, one clickable marker per claim.

This module is deliberately thin. Everything it shows comes from `ragqa.demo`,
which builds the pipeline once per process and returns plain dicts; this file only
turns those dicts into Chainlit objects. Keeping it thin is what lets the demo be
tested outside a browser.

Two details of Chainlit 2.3.0 shaped the wiring:

- There is no `cl.on_action`; the decorator that registers a click handler is
  `cl.action_callback(name)`.
- A custom element becomes a panel the moment its renderer is fetched from
  `/public/elements/<name>.jsx` and evaluated in the browser, so the renderer lives
  in `public/elements/CitationCard.jsx` and receives the panel as `props`.

The marker is an `Action`, not a link: a link would have to encode the whole
citation in a URL, and the chunk text is rebuilt from the index when the click
lands, so a marker can never show a stale copy of the evidence.
"""

from __future__ import annotations

import os
import sys

import chainlit as cl

try:  # imported as part of the package, via `python -m ragqa serve`
    from . import demo
except ImportError:  # chainlit loads this file by path, outside the package
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ragqa import demo

ACTION_OPEN_CITATION = "open_citation"
CITATION_ELEMENT = "CitationCard"


@cl.on_chat_start
async def on_chat_start() -> None:
    """State the configuration once, so the screen never lies about what it serves."""
    engine = demo.get_engine()
    await cl.Message(
        content=engine.describe()
        + "\n\nTry: _What state does a Vault server start in, and what can it not do "
        "in that state?_"
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    engine = demo.get_engine()
    response = await cl.make_async(engine.answer)(message.content or "")

    actions = [
        cl.Action(
            name=ACTION_OPEN_CITATION,
            label=claim["marker"],
            tooltip=f"{claim['doc_title']} > {claim['heading_path']}",
            payload=engine.citation_payload(claim),
        )
        for claim in response["claims"]
        if claim["verified"]
    ]
    await cl.Message(content=demo.render_answer(response), actions=actions).send()


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
