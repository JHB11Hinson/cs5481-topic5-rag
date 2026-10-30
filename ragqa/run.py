"""The single entry point: `python -m ragqa.run --config <path>`.

Walks the whole pipeline for one configuration and writes one immutable run
directory. Stages that are not implemented raise rather than silently
degrading, so a configuration can never quietly measure something else.

The pipeline as wired here, in order:

    documents -> chunks -> contextualization -> embeddings -> index
              -> sparse index -> retrieval (1..N hops) -> generation
              -> containment -> support judges -> metrics

Contextualization is one factor with three levels (`ADR-0006`): `plain` indexes
the chunk text, `contextual_prefix` indexes a generated sentence followed by the
chunk, `late_chunking` indexes a vector pooled from whole-document token states.
Only the dense representation differs for late chunking — the sparse branch always
sees real words, so a prefix's tokens are searchable and a late-chunked vector's
are not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

from . import chunk as chunk_mod
from . import config as config_mod
from . import corpus, embed, evaluate, generate, golden, index, judges, retrieve, verify
from . import agentic, context as context_mod
from .contract import PARTIAL_SUFFIX, RunContract, git_state
from .llm import LLMClient, LLMError


def _percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[int(round(fraction * (len(ordered) - 1)))])


def token_cost(tokens_in: int, tokens_out: int, price_in: float, price_out: float) -> float:
    """Dollars for one component: input at the input price, output at the output price."""
    return (
        int(tokens_in or 0) / 1e6 * float(price_in)
        + int(tokens_out or 0) / 1e6 * float(price_out)
    )


def cost_components(
    generation: Dict[str, Any],
    price_in: float,
    price_out: float,
    prefix: Optional[Dict[str, Any]] = None,
    rewrite: Optional[Dict[str, Any]] = None,
    judge: Optional[Dict[str, Any]] = None,
    judge_price_in: Optional[float] = None,
    judge_price_out: Optional[float] = None,
) -> Dict[str, Dict[str, float]]:
    """Tokens and dollars per component, each priced on both sides of the meter.

    Every component prices its completion tokens at the output price. Charging a
    component's output tokens at the input rate under-counts it by the ratio of the
    two prices (4x on the cheap model this matrix uses), which is how the published
    prefix figure was 23% too low.
    """
    entries = [("generation", generation, price_in, price_out)]
    if prefix is not None:
        entries.append(("prefix", prefix, price_in, price_out))
    if rewrite is not None:
        entries.append(("rewrite", rewrite, price_in, price_out))
    if judge is not None:
        # An unset or zero judge price means "the same rate as generation".
        entries.append(
            ("judge", judge, judge_price_in or price_in, judge_price_out or price_out)
        )

    components: Dict[str, Dict[str, float]] = {}
    for name, stats, in_price, out_price in entries:
        tokens_in = int(stats.get("tokens_in", 0) or 0)
        tokens_out = int(stats.get("tokens_out", 0) or 0)
        components[name] = {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "usd": token_cost(tokens_in, tokens_out, in_price, out_price),
        }
    return components


def _file_digest(path: str) -> Dict[str, Any]:
    """sha256 and size of one artifact, or a marker when it was never written."""
    if not os.path.exists(path):
        return {"sha256": "", "bytes": 0}
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "bytes": os.path.getsize(path)}


def run_id_for(cfg: config_mod.Config) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    digest = hashlib.sha256(
        json.dumps(cfg.nested(), sort_keys=True).encode("utf-8")
    ).hexdigest()[:8]
    return f"{cfg['run.name']}-{stamp}-{digest}"


def _llm_client(
    cfg: config_mod.Config, suffix: str = "", reasoning_effort: str = ""
) -> LLMClient:
    return LLMClient(
        base_url=cfg["llm.base_url"],
        cache_path=cfg["llm.cache_path"] + suffix,
        timeout=int(cfg["llm.timeout"]),
        temperature=float(cfg["llm.temperature"]),
        session_header=cfg["llm.session_header"],
        session_id=cfg["llm.session_id"],
        reasoning_effort=reasoning_effort,
    )


def _make_prefixer(cfg: config_mod.Config) -> context_mod.PrefixGenerator:
    concurrency = max(1, int(cfg["context.prefix_concurrency"]))
    effort = cfg["context.prefix_reasoning_effort"]
    client = _llm_client(cfg, ".prefix", reasoning_effort=effort)
    factory = None
    if concurrency > 1:
        factory = lambda: _llm_client(  # noqa: E731 - one handle per thread
            cfg, ".prefix", reasoning_effort=effort
        )
    return context_mod.PrefixGenerator(
        client=client,
        model=cfg["context.prefix_model"],
        cache_path=cfg["context.prefix_cache_path"],
        max_tokens=int(cfg["context.prefix_max_tokens"]),
        prompt_version=cfg["context.prefix_prompt_version"],
        concurrency=concurrency,
        client_factory=factory,
        effort_salt=effort,
    )


def execute(cfg: config_mod.Config, out_root: str) -> Dict[str, Any]:
    """Run one configuration, publishing the directory only once it is complete.

    ADR-0003 says a run either completes or leaves nothing behind, but a killed
    process cannot clean up after itself. So the work happens in `<run_id>.partial/`
    and the directory is renamed to `<run_id>/` only after `metrics.json` exists: a
    run directory with a `config.json` and no `metrics.json` never appears, and a
    process killed mid-run leaves a `.partial` that the next `execute` sweeps.
    """
    run_id = run_id_for(cfg)
    sweep_partials(out_root)
    contract = RunContract(out_root, run_id, partial=True)
    try:
        result = _execute(cfg, contract, run_id)
    except Exception:
        contract.discard()
        raise
    contract.finalize()
    result["run_dir"] = str(contract.path)
    return result


def sweep_partials(out_root: str) -> List[str]:
    """Delete `<run_id>.partial` directories left by a process that was killed.

    They hold work that never finished, which is exactly the state ADR-0003 says
    must not survive; nothing in them is evidence, because the evidence is the
    finished directory.
    """
    import shutil

    removed: List[str] = []
    if not out_root or not os.path.isdir(out_root):
        return removed
    for name in sorted(os.listdir(out_root)):
        if not name.endswith(PARTIAL_SUFFIX):
            continue
        path = os.path.join(out_root, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def item_context(
    cfg: config_mod.Config,
    retrieved: List[Dict[str, Any]],
    docs_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """What the generator is given, and what the verifier gets to check it against.

    The two are the same list on purpose. A baseline that hands the generator an
    empty retrieval block while the verifier still checks against the retrieved
    chunks makes every claim resolve to nothing, so its citation precision and
    recall are 0 by construction rather than by measurement.

    `baseline.long_context` builds one synthetic hit: the whole source document of
    the top-ranked chunk, truncated to the configured window, ranked 1, carrying the
    document's own id. It is marked `synthetic` so a reader of `predictions.jsonl`
    can see it is not a chunk — no chunker produced it.
    """
    prompt_hits = retrieved
    extra_context = ""

    if bool(cfg["baseline.closed_book"]):
        # Same generator, same prompt, empty retrieval block: the question is what
        # the model knows on its own, not what the corpus holds. Nothing was shown,
        # so nothing can be checked: claims against an empty context are unresolved
        # rather than unsupported.
        prompt_hits = []
    elif bool(cfg["baseline.long_context"]):
        top_doc_id = retrieved[0]["doc_id"] if retrieved else ""
        if top_doc_id:
            text = docs_by_id[top_doc_id]["text"][
                : int(cfg["baseline.long_context_max_chars"])
            ]
            prompt_hits = [
                {
                    "chunk_id": f"document:{top_doc_id}",
                    "doc_id": top_doc_id,
                    "rank": 1,
                    "score": float(retrieved[0].get("score", 0.0)),
                    "text": text,
                    "synthetic": True,
                }
            ]
        else:
            prompt_hits = []

    return {
        "prompt_hits": prompt_hits,
        "verify_hits": prompt_hits,
        "extra_context": extra_context,
    }


def _execute(cfg: config_mod.Config, contract: RunContract, run_id: str) -> Dict[str, Any]:
    docs = corpus.load_documents(cfg["corpus.source"])
    docs_by_id = {doc["doc_id"]: doc for doc in docs}
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

    # ---- contextualization -------------------------------------------------
    mode = cfg["context.mode"]
    context_stats: Dict[str, Any] = {"mode": mode}
    prefixer: Optional[context_mod.PrefixGenerator] = None
    if mode == "contextual_prefix":
        prefixer = _make_prefixer(cfg)
        prefixer.generate(
            children, docs_by_id, neighbours=int(cfg["context.prefix_neighbours"])
        )
        context_stats.update(prefixer.summary())
        index_texts = [child["contextual_text"] for child in children]
        context_mod.write_contextual_chunks(
            str(contract.path / "chunks_contextual.jsonl"), children
        )
    else:
        index_texts = [child["text"] for child in children]

    # ---- embeddings --------------------------------------------------------
    if mode == "late_chunking":
        embedder = embed.LateChunkingEmbedder(
            model_id=cfg["embed.model_id"]
            if cfg["embed.model_id"] != "stub-hashing"
            else "BAAI/bge-m3",
            device=cfg["embed.device"],
            max_seq_length=int(cfg["embed.late_max_seq_length"]),
            window_tokens=int(cfg["context.window_tokens"]),
            window_overlap=int(cfg["context.window_overlap"]),
            cache_path=cfg["embed.cache_path"],
        )
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for child in children:
            by_doc.setdefault(child["doc_id"], []).append(child)
        vectors_by_id: Dict[str, List[float]] = {}
        for doc_id, doc_children in by_doc.items():
            doc_children.sort(key=lambda c: c["char_start"])
            spans = [(c["char_start"], c["char_end"]) for c in doc_children]
            vectors = embedder.encode_document(docs_by_id[doc_id]["text"], spans)
            for child, vector in zip(doc_children, vectors):
                vectors_by_id[child["chunk_id"]] = vector
        ordered_vectors = [vectors_by_id[c["chunk_id"]] for c in children]
        embed_stats = dict(getattr(embedder, "last_stats", {}))
        context_stats.update(
            {
                "window_tokens": int(cfg["context.window_tokens"]),
                "window_overlap": int(cfg["context.window_overlap"]),
                "windows": embed_stats.get("windows", 0),
                "documents_over_window": embed_stats.get("documents_over_window", 0),
                "peak_vram_gb": round(embed_stats.get("peak_vram_bytes", 0) / 1e9, 2),
            }
        )
    else:
        embedder = embed.make(cfg)
        ordered_vectors = embedder.embed(index_texts)
        embed_stats = dict(getattr(embedder, "last_stats", {}))

    collection = (
        f"{cfg['corpus.snapshot_id']}-{cfg['chunk.strategy']}-{mode}"
    ).replace("/", "_")
    store = index.make(cfg, collection)
    store.add([c["chunk_id"] for c in children], ordered_vectors)
    index_seconds = time.perf_counter() - started

    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    sparse_index = None
    if cfg["retrieval.mode"] in ("hybrid", "rerank"):
        from .sparse import BM25Index

        # The sparse branch indexes the same text the dense branch embedded, so a
        # contextual prefix's tokens are searchable rather than merely adjacent.
        sparse_index = BM25Index()
        sparse_index.add([c["chunk_id"] for c in children], index_texts)

    generator = generate.make(cfg)
    judge_stack = judges.make(cfg)

    hop_threshold = cfg["retrieval.trigger_threshold"]
    if hop_threshold is None:
        hop_threshold = cfg["generate.abstain_score_threshold"]
    max_hops = int(cfg["retrieval.hops"])
    rewriter = None
    if max_hops > 1:
        # Rewriting is mechanical: no thinking channel, so a hop costs tokens for
        # queries rather than for deliberation.
        rewriter = agentic.Rewriter(
            _llm_client(cfg, ".rewrite", reasoning_effort="none"),
            model=cfg["retrieval.hop_rewrite_model"] or cfg["llm.model_generate"],
        )

    def retrieve_for_query(query: str) -> List[Dict[str, Any]]:
        query_vector = embedder.embed([query])[0]
        return retrieve.retrieve(
            store,
            chunks_by_id,
            query_vector,
            cfg["retrieval.mode"],
            int(cfg["retrieval.k"]),
            query=query,
            sparse=sparse_index,
            reranker=cfg["retrieval.reranker"],
            rerank_top=int(cfg["retrieval.rerank_top"]),
            rerank_max_length=int(cfg["retrieval.rerank_max_length"]),
            rrf_k=int(cfg["retrieval.rrf_k"]),
        )

    items = golden.load(cfg["golden.items_path"], cfg["golden.limit"])

    predictions: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    per_item: List[Dict[str, Any]] = []
    latencies: List[float] = []
    all_verdicts: List[Dict[str, Any]] = []
    hop_counts: Dict[str, int] = {}

    closed_book = bool(cfg["baseline.closed_book"])
    long_context = bool(cfg["baseline.long_context"])

    for item in items:
        began = time.perf_counter()
        retrieved, hop_meta = agentic.retrieve_with_hops(
            retrieve_for_query,
            item["question"],
            int(cfg["retrieval.k"]),
            float(hop_threshold),
            max_hops=max_hops,
            rewriter=rewriter,
            rrf_k=int(cfg["retrieval.rrf_k"]),
        )
        hop_counts[hop_meta["stop_reason"]] = hop_counts.get(hop_meta["stop_reason"], 0) + 1

        prompt_hits = retrieved
        extra_context = ""
        if closed_book or long_context:
            served = item_context(cfg, retrieved, docs_by_id)
            prompt_hits = served["prompt_hits"]
            extra_context = served["extra_context"]
        # The verifier sees exactly what the generator saw: a claim can only be
        # checked against a context the model was actually handed.
        verify_hits = prompt_hits

        answer = generator.generate(
            item,
            prompt_hits,
            float(cfg["generate.abstain_score_threshold"]),
            int(cfg["generate.max_claims"]),
            float(cfg["generate.min_claim_overlap"]),
            extra_context=extra_context,
        )
        if answer.get("parse_failure"):
            errors.append(
                {
                    "item_id": item["id"],
                    "class": "parse_failure",
                    "detail": (answer.get("raw_response") or "")[:200],
                }
            )
        verdicts = verify.check_claims(answer["claims"], verify_hits)
        if judge_stack is not None:
            for claim, verdict in zip(answer["claims"], verdicts):
                judge_stack.judge_claim(claim, verdict, verify_hits)
        all_verdicts.extend(verdicts)
        elapsed_ms = (time.perf_counter() - began) * 1000.0
        latencies.append(elapsed_ms)

        for claim, verdict in zip(answer["claims"], verdicts):
            citations.append(
                {
                    "item_id": item["id"],
                    "claim_id": claim["claim_id"],
                    "chunk_id": claim["chunk_id"],
                    "doc_id": claim["doc_id"],
                    # The verifier's span, not the generator's: a model cannot count
                    # characters, so a claim that arrives without a located span keeps
                    # its -1 sentinel, and a claim whose span the verifier placed
                    # carries the real offsets. Writing the generator's sentinel here
                    # made a rejected claim look like a span hit.
                    "span_start": (
                        verdict["span_start"]
                        if verdict.get("span_start") is not None
                        else claim.get("span_start", -1)
                    ),
                    "span_end": (
                        verdict["span_end"]
                        if verdict.get("span_end") is not None
                        else claim.get("span_end", -1)
                    ),
                    "quote": claim.get("quote", "")[:300],
                    "supported": verdict["supported"],
                    "error_class": verdict["error_class"],
                    "detail": verdict["detail"],
                    "containment_ok": verdict.get("containment_ok", verdict["error_class"] == ""),
                    "nli_supported": verdict.get("nli_supported"),
                    "nli_score": verdict.get("nli_score"),
                    "judge_supported": verdict.get("judge_supported"),
                    "judge_reason": verdict.get("judge_reason", ""),
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

        prediction = {
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
            "hop_stop_reason": hop_meta["stop_reason"],
            "hop_queries": hop_meta["queries"],
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
        if prompt_hits is not retrieved:
            # The prompt held something other than the retrieved chunks (closed
            # book, or the long-context baseline's whole document). Record what the
            # generator was actually shown, and mark a synthetic entry as synthetic:
            # its chunk_id names a document, and no chunker produced it.
            prediction["prompt_context"] = [
                {
                    "chunk_id": hit["chunk_id"],
                    "doc_id": hit["doc_id"],
                    "rank": hit["rank"],
                    "chars": len(hit.get("text") or ""),
                    "synthetic": bool(hit.get("synthetic", False)),
                }
                for hit in prompt_hits
            ]
        predictions.append(prediction)

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
                "hop_stop_reason": hop_meta["stop_reason"],
                "hops": hop_meta["hops"],
            }
        )

    metrics = evaluate.compute(items, per_item, int(cfg["retrieval.k"]))
    gen_stats = dict(getattr(generator, "last_stats", {}) or {})
    components = cost_components(
        generation={
            "tokens_in": gen_stats.get("tokens_in", 0),
            "tokens_out": gen_stats.get("tokens_out", 0),
        },
        price_in=float(cfg["llm.price_in_usd_per_mtok"]),
        price_out=float(cfg["llm.price_out_usd_per_mtok"]),
        prefix=prefixer.summary() if prefixer is not None else None,
        rewrite=(rewriter.last_stats if rewriter is not None else None),
        judge=(
            judge_stack.llm.last_stats
            if judge_stack is not None and judge_stack.llm is not None
            else None
        ),
        judge_price_in=float(cfg["llm.price_judge_in_usd_per_mtok"]),
        judge_price_out=float(cfg["llm.price_judge_out_usd_per_mtok"]),
    )
    cost_usd = sum(component["usd"] for component in components.values())
    metrics["system"].update(
        {
            "cost_usd": round(cost_usd, 6),
            "cost_cny": round(cost_usd * 6.67, 6),
            "cost_per_1k_questions_cny": round(
                cost_usd * 6.67 * (1000.0 / max(1, len(items))), 4
            ),
            "cost_components": {
                name: {**values, "usd": round(values["usd"], 6)}
                for name, values in components.items()
            },
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
            "context_mode": mode,
            "closed_book": closed_book,
            "long_context": long_context,
            "hops": max_hops,
            "judge_enabled": judge_stack is not None,
        }
    )
    metrics["grounding"] = evaluate.grounding_metrics(all_verdicts)
    if judge_stack is not None:
        metrics["grounding"]["judge_confusion"] = judges.confusion(all_verdicts)

    contract.write_json("config.json", cfg.nested())
    contract.write_json(
        "models.json",
        {
            "embed": {
                "provider": cfg["embed.provider"],
                "id": embedder.model_id,
                "version": getattr(embedder, "model_version", ""),
                "context_mode": mode,
            },
            "generate": {"provider": cfg["generate.provider"], "id": generator.model_id},
            "judge": (judge_stack.stats() if judge_stack is not None else None),
        },
    )
    contract.write_text(
        "git_sha.txt",
        json.dumps(git_state(), indent=2, sort_keys=True),
    )
    contract.write_json("corpus_snapshot.json", snapshot)
    contract.write_jsonl("chunks.jsonl", chunks)
    contract.write_json("chunk_stats.json", chunk_mod.stats(chunks))
    contract.write_json("context_stats.json", context_stats)
    contract.write_json(
        "hop_stats.json",
        {
            "max_hops": max_hops,
            "trigger_threshold": float(hop_threshold),
            "stop_reasons": hop_counts,
            "mean_hops": round(
                sum(entry.get("hops", 1) for entry in per_item) / max(1, len(per_item)), 4
            ),
        },
    )
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
            "prefix_cache_hits": (prefixer.last_stats.get("hits", 0) if prefixer else 0),
            "prefix_cache_misses": (prefixer.last_stats.get("misses", 0) if prefixer else 0),
            "note": "embedding cache: embeddings.sqlite; LLM cache: llm.sqlite",
        },
    )
    contract.write_json("metrics.json", metrics)

    # Large, re-derivable artifacts stay out of git (ADR-0003, spec item 5). The
    # checksums are committed so `scripts/fetch_artifacts.py` can rebuild a file and
    # prove it is the same one the numbers came from, instead of asking a reader to
    # trust a rebuild.
    contract.write_json(
        "artifacts.json",
        {
            "excluded_from_git": ["chunks.jsonl", "corpus_snapshot.json"],
            "checksums": {
                name: _file_digest(str(contract.path / name))
                for name in ("chunks.jsonl", "corpus_snapshot.json")
            },
            "rebuild": "python scripts/fetch_artifacts.py --run <this directory>",
        },
    )

    if prefixer is not None:
        prefixer.close()
    if judge_stack is not None:
        judge_stack.close()
    if rewriter is not None:
        rewriter.close()

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
