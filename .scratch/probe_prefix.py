import json
import urllib.request

from ragqa.llm import load_env

env = load_env()
base = env["LLM_BASE_URL"].rstrip("/")

def call(payload, label):
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + env["LLM_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "ragqa/0.1",
            "x-opencode-session": "probe-" + label,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())
    message = body["choices"][0]["message"]
    usage = body.get("usage", {})
    print(f"--- {label} usage={usage.get('completion_tokens')} reasoning={usage.get('completion_tokens_details')}")
    print("  content:", repr(str(message.get("content"))[:200]))
    print("  finish:", body["choices"][0].get("finish_reason"))


base_payload = {
    "model": "deepseek-v4.1-flash",
    "messages": [
        {"role": "system", "content": "Return valid json: {\"supported\": true|false, \"reason\": \"...\"}"},
        {"role": "user", "content": "CLAIM: the default is false\nSOURCE: The default is false."},
    ],
    "temperature": 0,
    "max_tokens": 200,
    "response_format": {"type": "json_object"},
    "reasoning_effort": "none",
}
call(base_payload, "json-none")
call({**base_payload, "model": "deepseek-v4-pro", "max_tokens": 400}, "pro-json-none")
