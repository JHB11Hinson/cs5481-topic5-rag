import time

from ragqa.llm import LLMClient

def client():
    return LLMClient(
        base_url="",
        cache_path="data/cache/llm.sqlite.probe",
        timeout=180,
        temperature=0.0,
        session_header="x-opencode-session",
        session_id="latency-probe",
        reasoning_effort="none",
    )

messages = [
    {"role": "system", "content": "You situate documentation excerpts in one sentence."},
    {"role": "user", "content": "Document: docs/concepts/seal\nSection: Seal\nExcerpt:\nVault starts sealed."},
]

c = client()
for i in range(3):
    began = time.perf_counter()
    result = c.complete("deepseek-v4.1-flash", messages + [{"role": "user", "content": f"variant {i}"}],
                        max_tokens=200, json_mode=False)
    print(f"seq {i}: {time.perf_counter() - began:.2f}s tokens_out={result['tokens_out']}")

from concurrent.futures import ThreadPoolExecutor

def one(i):
    began = time.perf_counter()
    cc = client()
    r = cc.complete("deepseek-v4.1-flash", messages + [{"role": "user", "content": f"concurrent {i}"}],
                    max_tokens=200, json_mode=False)
    cc.close()
    return time.perf_counter() - began, r["tokens_out"]

began = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as pool:
    for elapsed, tokens in pool.map(one, range(8)):
        print(f"par: {elapsed:.2f}s tokens_out={tokens}")
print(f"8 concurrent wall: {time.perf_counter() - began:.2f}s")
