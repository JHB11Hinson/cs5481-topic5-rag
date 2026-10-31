"""Conversation history for the demo, so a tab is not a memory hole.

The demo used to be stateless: one screen, one answer, and closing the tab threw the
conversation away. That is a usability defect in a demo that has to be shown live — you
cannot ask a follow-up, you cannot compare two questions side by side, and a reload
costs you the evidence you just built.

This module is a small, thread-safe SQLite store and nothing else. It knows about
conversations and messages; it does not know what Chainlit is, so it can be tested — and
it is, including from a second thread, because the demo serves answers from Chainlit's
worker threads while the store is built in the main one.

    store = ConversationStore("data/demo/history.sqlite")
    conversation = store.create("Vault sealing questions")
    store.append(conversation, "user", "What state does a Vault server start in?")
    store.append(conversation, "assistant", "It starts sealed.", payload={"claims": [...]})

Design decisions worth stating:

- **A message carries a rendered string plus an optional JSON payload.** The string is
  what the transcript shows; the payload is what makes a replayed answer clickable again
  (the citation markers), so history is not a read-only screenshot of an answer.
- **Ids are short and human-typable.** `/open c-1f4a9b2e` has to be possible by eye on a
  projector, so an id is a prefix and eight hex characters.
- **Deleting a conversation deletes its messages**, because a store that leaves orphans
  is a store whose `turns` column slowly stops meaning anything.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    payload         TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, id);
"""

MAX_TITLE = 80


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _title_from(text: str, fallback: str = "Untitled conversation") -> str:
    first = " ".join((text or "").split())
    if not first:
        return fallback
    if len(first) <= MAX_TITLE:
        return first
    return first[: MAX_TITLE - 1].rstrip() + "…"


class ConversationStore:
    """Conversations and their messages, in one file, safe to share across threads."""

    def __init__(self, path: str = "data/demo/history.sqlite"):
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---- conversations ----------------------------------------------------
    def create(self, title: str = "") -> str:
        conversation_id = "c-" + uuid.uuid4().hex[:8]
        stamp = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, _title_from(title), stamp, stamp),
            )
            self._conn.commit()
        return conversation_id

    def exists(self, conversation_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return row is not None

    def rename(self, conversation_id: str, title: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (_title_from(title), _now(), conversation_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._conn.commit()
        return cursor.rowcount > 0

    def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if row is None:
                return None
            turns = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()[0]
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "turns": int(turns),
        }

    def list(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                # `rowid` is the tiebreaker, not decoration: timestamps have one-second
                # resolution, so two conversations made in the same second used to come
                # back in whatever order the query planner felt like, and "newest first"
                # silently stopped meaning anything under a fast test or a busy click.
                "SELECT c.*, COUNT(m.id) AS turns FROM conversations c "
                "LEFT JOIN messages m ON m.conversation_id = c.id "
                "GROUP BY c.id ORDER BY c.updated_at DESC, c.created_at DESC, c.rowid DESC "
                "LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "turns": int(row["turns"]),
            }
            for row in rows
        ]

    def latest(self) -> Optional[str]:
        recent = self.list(limit=1)
        return recent[0]["id"] if recent else None

    # ---- messages ---------------------------------------------------------
    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add a turn. A conversation's first message may title it."""
        role = (role or "").strip() or "user"
        stamp = _now()
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload else None
        with self._lock:
            if not self.exists(conversation_id):
                raise KeyError(f"no such conversation: {conversation_id}")
            cursor = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, content, blob, stamp),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, conversation_id)
            )
            # An untitled conversation takes its title from the first user question, which
            # is how a history list stays recognisable without anyone naming anything.
            if role == "user":
                row = self._conn.execute(
                    "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
                if row is not None and row["title"] in ("", "Untitled conversation"):
                    self._conn.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (_title_from(content), conversation_id),
                    )
            self._conn.commit()
        return int(cursor.lastrowid)

    def messages(self, conversation_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, role, content, payload, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
                (conversation_id, max(1, int(limit))),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = None
            if row["payload"]:
                try:
                    payload = json.loads(row["payload"])
                except json.JSONDecodeError:
                    payload = None
            out.append(
                {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
