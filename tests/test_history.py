"""Conversation history for the demo: store, commands, replay.

Written after a live failure whose shape is worth remembering. The demo was stateless,
so a question that raised left the screen blank; and the caches it used were built in the
main thread and read from Chainlit's worker thread, so *every* question raised. Two tests
below pin the properties that fix depends on: the store works from another thread, and a
failing answer is stored as a message rather than disappearing.
"""

from __future__ import annotations

import os
import tempfile
import threading

from ragqa.history import ConversationStore


def _store() -> ConversationStore:
    directory = tempfile.mkdtemp(prefix="ragqa-history-")
    return ConversationStore(os.path.join(directory, "history.sqlite"))


def test_a_conversation_is_created_with_an_eyeballable_id():
    store = _store()
    conversation_id = store.create()
    assert conversation_id.startswith("c-")
    assert len(conversation_id) == 10
    assert store.exists(conversation_id)
    store.close()


def test_messages_come_back_in_order_with_their_payload():
    store = _store()
    conversation_id = store.create("payload round trip")
    store.append(conversation_id, "user", "first question")
    store.append(
        conversation_id,
        "assistant",
        "an answer with [1]",
        payload={"claims": [{"marker": "[1]", "payload": {"chunk_id": "c-abc"}}]},
    )
    turns = store.messages(conversation_id)
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    assert turns[1]["payload"]["claims"][0]["marker"] == "[1]"
    store.close()


def test_an_untitled_conversation_takes_its_title_from_the_first_question():
    store = _store()
    conversation_id = store.create()
    store.append(conversation_id, "user", "What state does a Vault server start in?")
    record = store.get(conversation_id)
    assert record["title"].startswith("What state does a Vault server")
    assert record["turns"] == 1
    store.close()


def test_a_long_question_is_truncated_into_a_title():
    store = _store()
    conversation_id = store.create()
    store.append(conversation_id, "user", "word " * 60)
    assert len(store.get(conversation_id)["title"]) <= 80
    store.close()


def test_history_lists_newest_first_and_deleting_takes_the_messages_with_it():
    store = _store()
    first = store.create("first")
    store.append(first, "user", "one")
    second = store.create("second")
    store.append(second, "user", "two")
    listing = store.list(limit=5)
    assert [row["id"] for row in listing][0] == second
    assert {row["id"] for row in listing} == {first, second}
    assert store.delete(first) is True
    assert store.messages(first) == []
    assert store.list(limit=5) == [row for row in store.list(limit=5) if row["id"] != first]
    store.close()


def test_appending_to_an_unknown_conversation_is_an_error_not_a_silent_write():
    store = _store()
    try:
        store.append("c-nosuch", "user", "hello")
    except KeyError as error:
        assert "c-nosuch" in str(error)
    else:
        raise AssertionError("a message was written to a conversation that does not exist")
    store.close()


def test_the_store_works_from_a_worker_thread():
    """The demo builds the store in the main thread and writes from Chainlit's workers."""
    store = _store()
    conversation_id = store.create("threads")
    outcome = {}

    def worker():
        try:
            store.append(conversation_id, "user", "from a worker")
            outcome["turns"] = store.get(conversation_id)["turns"]
        except Exception as exc:  # noqa: BLE001 - the failure is the assertion
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["turns"] == 1
    store.close()


def test_rename_and_latest_follow_the_store():
    store = _store()
    conversation_id = store.create()
    store.rename(conversation_id, "explicit title")
    assert store.get(conversation_id)["title"] == "explicit title"
    assert store.latest() == conversation_id
    store.close()


def test_a_failing_answer_becomes_a_stored_message():
    """What the adapter does on an exception: keep the turn, tell the reader."""
    store = _store()
    conversation_id = store.create()
    store.append(conversation_id, "user", "a question that will fail")
    store.append(
        conversation_id,
        "assistant",
        "**The answer did not arrive.** `RuntimeError: gateway closed`",
    )
    turns = store.messages(conversation_id)
    assert len(turns) == 2
    assert "did not arrive" in turns[1]["content"]
    assert store.get(conversation_id)["turns"] == 2
    store.close()
