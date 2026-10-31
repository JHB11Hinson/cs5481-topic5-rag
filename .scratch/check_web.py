"""Exercise the sidebar API over HTTP, the way the browser will."""

from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8100"


def call(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


print("--- create two conversations ---")
_, one = call("POST", "/api/conversations", {"title": "sidebar check"})
_, two = call("POST", "/api/conversations", {})
print("created:", one["id"], two["id"])

print("--- ask a real question in the first ---")
status, answer = call(
    "POST",
    f"/api/conversations/{one['id']}/ask",
    {"question": "What state does a Vault server start in, and what can it not do in that state?"},
)
response = answer["response"]
print("status:", status, "| claims:", len(response["claims"]), "| verified:", response["verified_claims"],
      "| abstained:", response["abstained"])
citation = answer["payload"]["claims"][0]["citation"] if answer["payload"]["claims"] else None
print("first marker:", answer["payload"]["claims"][0]["marker"] if citation else "none")

print("--- open the citation panel ---")
if citation:
    status, props = call("POST", "/api/citation", {"payload": citation})
    print("status:", status, "| doc:", props.get("doc_title"), "| heading:", props.get("heading_path"))
    print("span:", repr(props.get("span_text"))[:70])
    print("html has mark:", "<mark>" in props.get("chunk_html", ""))

print("--- replay it ---")
status, replay = call("GET", f"/api/conversations/{one['id']}")
print("status:", status, "| turns:", len(replay["messages"]),
      "| roles:", [m["role"] for m in replay["messages"]],
      "| payload kept:", bool(replay["messages"][-1]["payload"]))

print("--- list ---")
status, listing = call("GET", "/api/conversations")
print("status:", status, "| conversations:", [(row["id"], row["title"][:40]) for row in listing["conversations"]])

print("--- bulk delete both plus a ghost ---")
status, deleted = call("DELETE", "/api/conversations", {"ids": [one["id"], two["id"], "c-ghost"]})
print("status:", status, "| deleted:", deleted["deleted"], "| missing:", deleted["missing"])

status, listing = call("GET", "/api/conversations")
print("after delete:", len(listing["conversations"]), "conversation(s)")
