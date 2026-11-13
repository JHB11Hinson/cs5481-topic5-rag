"""A DeepSeek-shaped web surface: a conversation sidebar with multi-select delete.

Why this exists next to `chainlit_app.py`. Chainlit 2.3.0 gives a chat stream and a
custom-element panel, but not the thing a live demo actually wants: a **sidebar** of
conversations you can create, switch between, rename, and delete in bulk. Its own thread
list needs a data layer (`aiohttp`, `sqlalchemy`, `alembic`) and offers single deletion
only; its custom elements cannot call back into the server at all, so a checkbox list
cannot be built inside it. Rather than fork its frontend, this module serves one page and
a small JSON API from the standard library, and reuses `ragqa.demo` for the pipeline and
`ragqa.history` for the store, so both surfaces speak the same code.

    python -m ragqa serve --config configs/... --backend web --port 8100

Endpoints (all JSON):

    GET    /api/config                      what is being served
    GET    /api/conversations               list, newest first
    POST   /api/conversations               create {title?} -> conversation
    PATCH  /api/conversations/<id>          rename {title}
    DELETE /api/conversations               bulk delete {ids: [...]} -> {deleted, missing}
    GET    /api/conversations/<id>          messages, for replay
    POST   /api/conversations/<id>/ask      {question} -> answer + stored turns
    POST   /api/citation                    {payload} -> the source panel's props

The pipeline is single-tenant (one GPU, one embedded index), so `/ask` takes a lock and a
second tab's question queues rather than colliding. Bulk delete validates ids and reports
which ones did not exist instead of silently succeeding, because a delete that lies is
worse than one that refuses.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import demo

ASSET_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "web")
ANSWER_LOCK = threading.Lock()
MAX_BODY = 64 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _store():
    return demo.get_history(os.environ.get(demo._HISTORY_ENV, demo.DEFAULT_HISTORY))


# --------------------------------------------------------------------------- #
# API surface, as plain functions so the tests need no socket
# --------------------------------------------------------------------------- #


def api_config() -> Dict[str, Any]:
    engine = demo.get_engine()
    return {
        "configuration": engine.config_name,
        "snapshot": engine.snapshot_id,
        "chunks": engine.chunk_count,
        "retrieval": engine.cfg["retrieval.mode"],
        "k": engine.k,
        "generator": getattr(engine.generator, "model_id", "?"),
        "build_seconds": round(engine.build_seconds, 1),
    }


def api_list() -> List[Dict[str, Any]]:
    return _store().list(limit=200)


def api_create(title: str = "") -> Dict[str, Any]:
    store = _store()
    conversation_id = store.create(title)
    return store.get(conversation_id) or {"id": conversation_id, "title": title, "turns": 0}


def api_rename(conversation_id: str, title: str) -> Dict[str, Any]:
    store = _store()
    if not store.rename(conversation_id, title):
        raise ApiError(404, f"no conversation {conversation_id}")
    return store.get(conversation_id) or {}


def api_delete(ids: List[str]) -> Dict[str, Any]:
    """Bulk delete. Unknown ids are reported, never assumed deleted."""
    if not isinstance(ids, list) or not ids:
        raise ApiError(400, "ids must be a non-empty list")
    store = _store()
    deleted: List[str] = []
    missing: List[str] = []
    for conversation_id in ids:
        if not isinstance(conversation_id, str) or not conversation_id:
            missing.append(str(conversation_id))
            continue
        if store.delete(conversation_id):
            deleted.append(conversation_id)
        else:
            missing.append(conversation_id)
    return {"deleted": deleted, "missing": missing}


def api_messages(conversation_id: str) -> Dict[str, Any]:
    store = _store()
    record = store.get(conversation_id)
    if record is None:
        raise ApiError(404, f"no conversation {conversation_id}")
    return {"conversation": record, "messages": store.messages(conversation_id)}


def api_ask(conversation_id: str, question: str) -> Dict[str, Any]:
    question = (question or "").strip()
    if not question:
        raise ApiError(400, "question must not be empty")
    store = _store()
    if store.get(conversation_id) is None:
        raise ApiError(404, f"no conversation {conversation_id}")

    store.append(conversation_id, "user", question)
    engine = demo.get_engine()
    with ANSWER_LOCK:
        response = engine.answer(question)

    rendered = demo.render_answer(response)
    payload = {
        "config_name": response["config_name"],
        "abstained": response["abstained"],
        "answer_mode": response.get("answer_mode", "abstained" if response["abstained"] else "grounded"),
        "abstain_reason": response["abstain_reason"],
        "retrieval_ms": response["retrieval_ms"],
        "generation_ms": response["generation_ms"],
        "claims": [
            {
                "marker": claim["marker"],
                "verified": claim["verified"],
                "doc_title": claim["doc_title"],
                "heading_path": claim["heading_path"],
                "citation": engine.citation_payload(claim),
            }
            for claim in response["claims"]
            if claim["verified"]
        ],
    }
    store.append(conversation_id, "assistant", rendered, payload=payload)
    return {
        "conversation": store.get(conversation_id),
        "response": response,
        "rendered": rendered,
        "payload": payload,
    }


def api_citation(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("chunk_id"):
        raise ApiError(400, "payload must carry a chunk_id")
    engine = demo.get_engine()
    try:
        return engine.citation_props(payload)
    except (KeyError, ValueError) as error:
        raise ApiError(404, str(error)) from error


# --------------------------------------------------------------------------- #
# HTTP plumbing
# --------------------------------------------------------------------------- #

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ragqa-demo/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quieter than the default
        if os.environ.get("RAGQA_WEB_VERBOSE"):
            super().log_message(fmt, *args)

    # ---- helpers ---------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ApiError(413, "request body too large")
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(400, f"invalid JSON body: {error}") from error
        if not isinstance(parsed, dict):
            raise ApiError(400, "request body must be an object")
        return parsed

    def _static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        target = os.path.normpath(os.path.join(ASSET_ROOT, relative))
        if not target.startswith(os.path.normpath(ASSET_ROOT) + os.sep) and target != os.path.normpath(ASSET_ROOT):
            self._json(403, {"error": "path outside the asset root"})
            return
        if not os.path.isfile(target):
            self._json(404, {"error": f"no such asset: {path}"})
            return
        extension = os.path.splitext(target)[1].lower()
        with open(target, "rb") as handle:
            body = handle.read()
        self._send(200, body, CONTENT_TYPES.get(extension, "application/octet-stream"))

    # ---- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                self._json(200, api_config())
            elif path == "/api/conversations":
                self._json(200, {"conversations": api_list()})
            elif path.startswith("/api/conversations/"):
                self._json(200, api_messages(path.rsplit("/", 1)[-1]))
            elif path.startswith("/api/"):
                self._json(404, {"error": f"no such endpoint: {path}"})
            else:
                self._static(path)
        except ApiError as error:
            self._json(error.status, {"error": error.message})
        except Exception as error:  # noqa: BLE001 - the browser gets a reason, not a blank page
            self._json(500, {"error": f"{type(error).__name__}: {error}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/conversations":
                self._json(200, api_create(str(body.get("title") or "")))
            elif path == "/api/conversations/ask":
                self._json(200, api_ask(str(body.get("conversation_id") or ""), str(body.get("question") or "")))
            elif path.endswith("/ask") and path.startswith("/api/conversations/"):
                conversation_id = path[len("/api/conversations/"): -len("/ask")]
                self._json(200, api_ask(conversation_id, str(body.get("question") or "")))
            elif path == "/api/citation":
                self._json(200, api_citation(body.get("payload") or {}))
            elif path == "/api/conversations/bulk-delete":
                self._json(200, api_delete(body.get("ids") or []))
            else:
                self._json(404, {"error": f"no such endpoint: {path}"})
        except ApiError as error:
            self._json(error.status, {"error": error.message})
        except Exception as error:  # noqa: BLE001
            self._json(500, {"error": f"{type(error).__name__}: {error}"})

    def do_PATCH(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/conversations/"):
                conversation_id = path.rsplit("/", 1)[-1]
                body = self._body()
                self._json(200, api_rename(conversation_id, str(body.get("title") or "")))
            else:
                self._json(404, {"error": f"no such endpoint: {path}"})
        except ApiError as error:
            self._json(error.status, {"error": error.message})
        except Exception as error:  # noqa: BLE001
            self._json(500, {"error": f"{type(error).__name__}: {error}"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/conversations":
                body = self._body()
                self._json(200, api_delete(body.get("ids") or []))
            else:
                self._json(404, {"error": f"no such endpoint: {path}"})
        except ApiError as error:
            self._json(error.status, {"error": error.message})
        except Exception as error:  # noqa: BLE001
            self._json(500, {"error": f"{type(error).__name__}: {error}"})


def serve(config_path: str, host: str = "127.0.0.1", port: int = 8100) -> int:
    os.environ[demo.CONFIG_ENV] = os.path.abspath(config_path)
    engine = demo.install_engine(demo.ChatEngine.from_config(config_path))
    print(
        f"demo(web): configuration {engine.config_name!r} "
        f"({engine.chunk_count} chunks, {engine.index_backend} index) "
        f"loaded in {engine.build_seconds:.1f}s"
    )
    history = _store()
    print(f"demo(web): history at {history.path}")
    server = ThreadingHTTPServer((host, int(port)), Handler)
    print(f"demo(web): serving http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
