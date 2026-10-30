"""The single entry point: `python -m ragqa.run --config <path>`.

Walks the whole pipeline for one configuration and writes one immutable run
directory. Stages that are not implemented yet raise rather than silently
degrading, so a configuration can never quietly measure something else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Any, Dict, List

from . import chunk as chunk_mod
from . import config as config_mod
from . import corpus, embed, evaluate, generate, golden, index, retrieve, verify
from .contract import RunContract, git_state
from .llm import LLMError


def _percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[int(round(fraction * (len(ordered) - 1)))])


def run_id_for(cfg: config_mod.Config) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    digest = hashlib.sha256(
        json.dumps(cfg.nested(), sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]
    return f"{cfg['run.name']}-{stamp}-{digest}"


def execute(cfg: config_mod.Config, out_root: str) -> Dict[str, Any]:
    run_id = run_id_for(cfg)
    contract = RunContract(out_root, run_id)
    try:
        return _execute(cfg, contract, run_id)
    except Exception:
        # A run directory that exists without metrics.json is a lie about what was
        # measured (ADR-0003): either the run completed or it left nothing behind.
        import shutil

        shutil.rmtree(contract.path, ignore_errors=True)
        raise


def _execute(cfg: config_mod.Config, contract: RunContract, run_id: str) -> Dict[str, Any]:
    docs = corpus.load_documents(cfg["corpus.source"])
    snapshot = corpus.snapshot_identity(docs, cfg["corpus.snapshot_id"])

    started = time.perf_counter()
    chunks = chunk_mod.build(
        docs,
        cfg["chunk.strategy"],
        int(cfg["chunk.size"]),
        int(cfg["chunk.overlap"]),
        int(cfg["chunk.parent_size"]),
    )
    children = [c for c in chunks if c["kind"] == "child"]
    if not children:
        raise SystemExit("chunking produced no child chunks")

    if cfg["context.mode"] == "late_chunking":
        late = embed.LateChunkingEmbedder(
            model_id=cfg["embed.model_id"] if cfg["embed.model_id"] != "stub-hashing" else "BAAI/bge-m3",
            device=cfg["embed.device"],
            max_seq_length=int(cfg["embed.late_max_seq_length"]),
            cache_path=cfg["embed.cache_path"],
        )
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for child in children:
            by_doc.setdefault(child["doc_id"], []).append(child)
        vectors_by_id: Dict[str, List[float]] = {}
        docs_by_id = {doc["doc_id"]: doc for doc in docs}
        for doc_id, doc_children in by_doc.items():
            spans = [(c["char_start"], c["char_end"]) for c in doc_children]
            vectors = late.encode_document(docs_by_id[doc_id]["text"], spans)
            for child, vector in zip(doc_children, vectors):
                vectors_by_id[child["chunk_id"]] = vector
        embedder = late
        embed_stats = dict(late.last_stats)
        ordered_vectors = [vectors_by_id[c["chunk_id"]] for c in children]
    else:
        embedder = embed.make(cfg)
        ordered_vectors = embedder.embed([c["text"] for c in children])
        embed_stats = dict(getattr(embedder, "last_stats", {}))
    collection = f"{cfg['corpus.snapshot_id']}-{cfg['chunk.strategy']}-{cfg['context.mode']}".replace("/", "_")
    store = index.make(cfg, collection)
    store.add([c["chunk_id"] for c in children], ordered_vectors)
    index_seconds = time.perf_counter() - started

    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    children_by_id = {c["chunk_id"]: c for c in children}
    sparse_index = None
    if cfg["retrieval.mode"] in ("hybrid", "rerank"):
        from .sparse import BM25Index

        sparse_index = BM25Index()
        sparse_index.add(
            [c["chunk_id"] for c in children], [c["text"] for c in children]
        )
    generator = generate.make(cfg)

    items = golden.load(cfg["golden.items_path"], cfg["golden.limit"])

    predictions: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    per_item: List[Dict[str, Any]] = []
    latencies: List[float] = []

    for item in items:
        began = time.perf_counter()
        query_vector = embedder.embed([item["question"]])[0]
        retrieved = retrieve.retrieve(
            store,
            chunks_by_id,
            query_vector,
            cfg["retrieval.mode"],
            int(cfg["retrieval.k"]),
            query=item["question"],
            sparse=sparse_index,
            reranker=cfg["retrieval.reranker"],
            rerank_top=int(cfg["retrieval.rerank_top"]),
            rerank_max_length=int(cfg["retrieval.rerank_max_length"]),
            rrf_k=int(cfg["retrieval.rrf_k"]),
        )
        answer = generator.generate(
            item,
            retrieved,
            float(cfg["generate.abstain_score_threshold"]),
            int(cfg["generate.max_claims"]),
            float(cfg["generate.min_claim_overlap"]),
        )
        if answer.get("parse_failure"):
            errors.append(
                {
                    "item_id": item["id"],
                    "class": "parse_failure",
                    "detail": (answer.get("raw_response") or "")[:200],
                }
            )
        verdicts = verify.check_claims(answer["claims"], retrieved)
        elapsed_ms = (time.perf_counter() - began) * 1000.0
        latencies.append(elapsed_ms)

        for claim, verdict in zip(answer["claims"], verdicts):
            citations.append(
                {
                    "item_id": item["id"],
                    "claim_id": claim["claim_id"],
                    "chunk_id": claim["chunk_id"],
                    "doc_id": claim["doc_id"],
                    "span_start": claim.get("span_start", -1),
                    "span_end": claim.get("span_end", -1),
                    "quote": claim.get("quote", "")[:300],
                    "supported": verdict["supported"],
                    "error_class": verdict["error_class"],
                    "detail": verdict["detail"],
                }
            )
        for verdict in verdicts:
            if not verdict["supported"]:
                errors.append(
                    {
                        "item_id": item["id"],
                        "class": verdict["error_class"],
                        "detail": verdict["detail"],
                    }
                )

        predictions.append(
            {
                "item_id": item["id"],
                "answerable": bool(item.get("answerable", True)),
                "answer_text": answer["answer_text"],
                "abstained": answer["abstained"],
                "abstain_reason": answer["abstain_reason"],
                "claims": answer["claims"],
                "raw_response": (answer.get("raw_response") or "")[:2000],
                "tokens_in": answer.get("tokens_in", 0),
                "tokens_out": answer.get("tokens_out", 0),
                "citation_chunk_ids": [c["chunk_id"] for c in answer["citations"]],
                "retrieved": [
                    {
                        "chunk_id": hit["chunk_id"],
                        "doc_id": hit["doc_id"],
                        "rank": hit["rank"],
                        "score": round(hit["score"], 6),
                    }
                    for hit in retrieved
                ],
            }
        )

        per_item.append(
            {
                "item_id": item["id"],
                "answerable": bool(item.get("answerable", True)),
                "abstained": answer["abstained"],
                "claims": answer["claims"],
                "verdicts": verdicts,
                "retrieved": retrieved,
                "quotes": [e.get("quote", "") for e in item.get("evidence", [])],
                "latency_ms": elapsed_ms,
            }
        )

    metrics = evaluate.compute(items, per_item, int(cfg["retrieval.k"]))
    gen_stats = dict(getattr(generator, "last_stats", {}) or {})
    price_in = float(cfg["llm.price_in_usd_per_mtok"])
    price_out = float(cfg["llm.price_out_usd_per_mtok"])
    cost_usd = (
        gen_stats.get("tokens_in", 0) / 1e6 * price_in
        + gen_stats.get("tokens_out", 0) / 1e6 * price_out
    )
    metrics["system"].update(
        {
            "cost_usd": round(cost_usd, 6),
            "cost_cny": round(cost_usd * 6.67, 6),
            "cost_per_1k_questions_cny": round(cost_usd * 6.67 * (1000.0 / max(1, len(items))), 4),
        }
    )
    metrics["system"].update(
        {
            "index_bytes": store.size_bytes(),
            "index_backend": store.backend,
            "chunks_indexed": store.count(),
            "generation_calls": len(items),
            "embedding_model": embedder.model_id,
            "generator_model": generator.model_id,
        }
    )

    contract.write_json("config.json", cfg.nested())
    contract.write_json("models.json", {
        "embed": {"provider": cfg["embed.provider"], "id": embedder.model_id,
                  "version": getattr(embedder, "model_version", "")},
        "generate": {"provider": cfg["generate.provider"], "id": generator.model_id},
    })
    contract.write_text(
        "git_sha.txt",
        json.dumps(git_state(), indent=2, sort_keys=True),
    )
    contract.write_json("corpus_snapshot.json", snapshot)
    contract.write_jsonl("chunks.jsonl", chunks)
    contract.write_json("chunk_stats.json", chunk_mod.stats(chunks))
    contract.write_jsonl("predictions.jsonl", predictions)
    contract.write_jsonl("citations.jsonl", citations)
    contract.write_jsonl("errors.jsonl", errors)
    contract.write_json(
        "timings.json",
        {
            "index_build_seconds": round(index_seconds, 4),
            "per_item_ms": [round(value, 3) for value in latencies],
            "p50_ms": round(_percentile(latencies, 0.5), 3),
            "p95_ms": round(_percentile(latencies, 0.95), 3),
            "total_wall_seconds": round(time.perf_counter() - started, 4),
        },
    )
    contract.write_json(
        "cache_stats.json",
        {
            "embed_cache_hits": embed_stats.get("hits", 0),
            "embed_cache_misses": embed_stats.get("misses", len(children)),
            "llm_cache_hits": gen_stats.get("hits", 0),
            "llm_cache_misses": gen_stats.get("misses", 0),
            "llm_tokens_in": gen_stats.get("tokens_in", 0),
            "llm_tokens_out": gen_stats.get("tokens_out", 0),
            "note": "embedding cache: embeddings.sqlite; LLM cache: llm.sqlite",
        },
    )
    contract.write_json("metrics.json", metrics)

    return {
        "run_id": run_id,
        "run_dir": str(contract.path),
        "metrics": metrics,
        "missing": contract.missing(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ragqa.run", description="Execute one configuration.")
    parser.add_argument("--config", required=True, help="path to a YAML configuration")
    parser.add_argument("--out", default=None, help="run output root (default: run.out_root)")
    parser.add_argument("--items", type=int, default=None, help="truncate the golden set")
    parser.add_argument("--allow-dirty", action="store_true", help="run on a dirty git tree")
    return parser


def main(argv: List[str] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_mod.load(args.config)
    if args.items:
        cfg = config_mod.Config({**cfg.as_dict(), "golden.limit": int(args.items)})

    state = git_state()
    if state["dirty"] and not args.allow_dirty:
        print(
            f"refusing to run: working tree is dirty ({state['sha']}). "
            "Commit or pass --allow-dirty.",
            file=sys.stderr,
        )
        return 2

    out_root = args.out or cfg["run.out_root"]
    if cfg["retrieval.mode"] == "rerank" and int(cfg["retrieval.rerank_top"]) < int(cfg["retrieval.k"]):
        print(
            "refusing to run: retrieval.rerank_top ({}) is below retrieval.k ({}), so "
            "recall@k would measure truncation rather than retrieval (ADR-0011)".format(
                cfg["retrieval.rerank_top"], cfg["retrieval.k"]
            ),
            file=sys.stderr,
        )
        return 2
    try:
        result = execute(cfg, out_root)
    except LLMError as error:
        print(f"generation unavailable: {error}", file=sys.stderr)
        print(
            "the pipeline ran up to generation and left no run directory behind "
            "(ADR-0003); re-run once the gateway is funded",
            file=sys.stderr,
        )
        return 4
    if result["missing"]:
        print(f"run contract incomplete, missing: {result['missing']}", file=sys.stderr)
        return 3

    metrics = result["metrics"]
    print(f"run: {result['run_id']}")
    print(f"dir: {result['run_dir']}")
    print(
        "retrieval  hit@{k}={hit}  mrr={mrr}  ndcg@10={ndcg}".format(
            k=metrics["retrieval"]["k"],
            hit=metrics["retrieval"]["hit_rate"],
            mrr=metrics["retrieval"]["mrr"],
            ndcg=metrics["retrieval"]["ndcg_at_10"],
        )
    )
    print(
        "citations  precision={p}  recall={r}  span_hit={s}  failures={f}".format(
            p=metrics["citations"]["citation_precision"],
            r=metrics["citations"]["citation_recall"],
            s=metrics["citations"]["span_hit_rate"],
            f=metrics["citations"]["containment_failures"],
        )
    )
    print(
        "abstention over={o}  negatives_caught={n}/{t}".format(
            o=metrics["abstention"]["over_abstain_rate"],
            n=metrics["abstention"]["abstained_unanswerable"],
            t=metrics["items"]["unanswerable"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
