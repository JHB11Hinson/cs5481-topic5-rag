"""The single-screen demo: one configuration, loaded once, answering interactively.

`ragqa.run` measures a configuration over a golden set and writes it down.
`ragqa.demo` serves *one* configuration to a person: the same corpus, the same
chunks, the same embedder, index, sparse branch, retriever and generator that
`run._execute` wires together, built once at process start and then reused for
every question. Reloading bge-m3 or rebuilding the index per message would turn a
demo into a load test, so the engine owns them for the life of the process.

What the screen shows is deliberately narrower than what the model says: every
claim goes through `verify.check_claims` first, and a claim whose quote is not in
the chunk it cites is rendered as unverified rather than quietly dropped or
quietly trusted (`ADR-0004`). A citation the pipeline cannot defend is not a
citation, and the demo is where that distinction has to be visible.

This module holds no Chainlit code: `answer()` returns plain dicts and
`render_answer()` returns markdown, so the whole surface is testable in-process.
`ragqa/chainlit_app.py` is the thin adapter that turns a click into a panel.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import time
from typing import Any, Dict, List, Optional

from . import agentic, chunk as chunk_mod, config as config_mod, corpus, embed
from . import generate, index, retrieve, verify

DEFAULT_CONFIG = "configs/smoke.yaml"
CONFIG_ENV = "RAGQA_DEMO_CONFIG"
ABSTAIN_MESSAGE = (
    "The documentation provided does not contain an answer to this question."
)


def _one_line(text: str, limit: int = 320) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "..."


def _source_line(hit: Dict[str, Any]) -> str:
    where = f" > {hit['heading_path']}" if hit.get("heading_path") else ""
    url = f" - {hit['url']}" if hit.get("url") else ""
    return f"**{hit.get('doc_title') or hit['doc_id']}**{where}{url}"


def render_answer(response: Dict[str, Any]) -> str:
    """Markdown for one answer: claims with markers, or the abstention case."""
    footer = (
        f"_Retrieval {response['retrieval_ms']:.0f} ms | generation "
        f"{response['generation_ms']:.0f} ms | configuration "
        f"`{response['config_name']}`_"
    )

    if response["abstained"]:
        lines = [f"**Abstained.** {ABSTAIN_MESSAGE}", "", response["insufficiency"], ""]
        best = response["best_chunk"]
        if best is not None:
            lines.append(
                f"Best retrieved chunk: {_source_line(best)} "
                f"(chunk `{best['chunk_id']}`, score {best['score']:.3f})"
            )
            lines.extend(["", f"> {_one_line(best['text'])}"])
        lines.extend(["", "---", footer])
        return "\n".join(lines)

    claims = response["claims"]
    verified = [claim for claim in claims if claim["verified"]]
    withheld = [claim for claim in claims if not claim["verified"]]
    lines = [
        f"**Answer** - {len(verified)} of {len(claims)} claims carry a verified "
        f"citation."
    ]
    if not claims:
        lines.append("")
        lines.append("_The generator returned no claim at all._")
    for index, claim in enumerate(verified, start=1):
        lines.append(f"{index}. {claim['text']} {claim['marker']}")
    if withheld:
        lines.append("")
        lines.append("**Withheld - citation did not contain the claim:**")
        for claim in withheld:
            lines.append(
                f"- {claim['text']} - `{claim['error_class']}`, citing "
                f"`{claim['chunk_id']}` ({claim['detail']})"
            )
    if response["hops"] > 1:
        lines.append("")
        lines.append(
            f"_Retrieval took {response['hops']} hops "
            f"({response['hop_stop_reason']})._"
        )
    lines.extend(["", "---", footer])
    return "\n".join(lines)


class ChatEngine:
    """One configuration, loaded once: chunks, embedder, index, generator."""

    def __init__(self, cfg: config_mod.Config, generator: Optional[object] = None):
        self.cfg = cfg
        self.config_name = str(cfg["run.name"])
        self.snapshot_id = str(cfg["corpus.snapshot_id"])
        self.context_mode = str(cfg["context.mode"])
        if self.context_mode != "plain":
            # The other two levels index something the chunk text is not (a
            # generated prefix, a pooled document vector), and their build paths
            # live in `run._execute`. Serving them from here would mean a second
            # variant of that wiring, which is the thing this ticket avoids.
            raise ValueError(
                "the demo serves context.mode=plain configurations; "
                f"{self.context_mode!r} is only wired in ragqa.run"
            )

        started = time.perf_counter()
        self.docs = corpus.load_documents(cfg["corpus.source"])
        self.docs_by_id = {doc["doc_id"]: doc for doc in self.docs}
        self.chunks = chunk_mod.build(
            self.docs,
            cfg["chunk.strategy"],
            int(cfg["chunk.size"]),
            int(cfg["chunk.overlap"]),
            int(cfg["chunk.parent_size"]),
        )
        self.children = [c for c in self.chunks if c["kind"] == "child"]
        if not self.children:
            raise ValueError("chunking produced no child chunks")
        self.chunks_by_id = {c["chunk_id"]: c for c in self.chunks}

        self.embedder = embed.make(cfg)
        vectors = self.embedder.embed([child["text"] for child in self.children])
        collection = (
            f"{self.snapshot_id}-{cfg['chunk.strategy']}-{self.context_mode}"
        ).replace("/", "_")
        self.store = index.make(cfg, collection)
        self.store.add([c["chunk_id"] for c in self.children], vectors)

        self.sparse = None
        if cfg["retrieval.mode"] in ("hybrid", "rerank"):
            from .sparse import BM25Index

            self.sparse = BM25Index()
            self.sparse.add(
                [c["chunk_id"] for c in self.children],
                [c["text"] for c in self.children],
            )

        self.generator = generator if generator is not None else generate.make(cfg)
        self.threshold = float(cfg["generate.abstain_score_threshold"])
        self.max_claims = int(cfg["generate.max_claims"])
        self.min_claim_overlap = float(cfg["generate.min_claim_overlap"])
        self.k = int(cfg["retrieval.k"])
        self.rrf_k = int(cfg["retrieval.rrf_k"])
        self.max_hops = int(cfg["retrieval.hops"])
        self.rewriter = None
        if self.max_hops > 1:
            from .run import _llm_client

            self.rewriter = agentic.Rewriter(
                _llm_client(cfg, ".rewrite", reasoning_effort="none"),
                model=cfg["retrieval.hop_rewrite_model"] or cfg["llm.model_generate"],
            )
        self.build_seconds = time.perf_counter() - started

    # ---- identity ---------------------------------------------------------
    @property
    def chunk_count(self) -> int:
        return len(self.children)

    @property
    def index_backend(self) -> str:
        return str(getattr(self.store, "backend", ""))

    @classmethod
    def from_config(cls, path: str) -> "ChatEngine":
        return cls(config_mod.load(path))

    # ---- one question -----------------------------------------------------
    def _retrieve_for_query(self, query: str) -> List[Dict[str, Any]]:
        vector = self.embedder.embed([query])[0]
        return retrieve.retrieve(
            self.store,
            self.chunks_by_id,
            vector,
            self.cfg["retrieval.mode"],
            self.k,
            query=query,
            sparse=self.sparse,
            reranker=self.cfg["retrieval.reranker"],
            rerank_top=int(self.cfg["retrieval.rerank_top"]),
            rerank_max_length=int(self.cfg["retrieval.rerank_max_length"]),
            rrf_k=self.rrf_k,
        )

    def answer(self, question: str) -> Dict[str, Any]:
        """One question end to end; the response is everything the screen shows."""
        question = (question or "").strip()
        item_id = "q-" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:8]

        began = time.perf_counter()
        hits, hop_meta = agentic.retrieve_with_hops(
            self._retrieve_for_query,
            question,
            self.k,
            self.threshold,
            max_hops=self.max_hops,
            rewriter=self.rewriter,
            rrf_k=self.rrf_k,
        )
        retrieval_ms = (time.perf_counter() - began) * 1000.0

        began = time.perf_counter()
        generated = self.generator.generate(
            {"id": item_id, "question": question},
            hits,
            self.threshold,
            self.max_claims,
            self.min_claim_overlap,
        )
        verdicts = verify.check_claims(generated["claims"], hits)
        generation_ms = (time.perf_counter() - began) * 1000.0

        claims = self._claim_views(generated["claims"], verdicts)
        shown = hits[:3]
        response: Dict[str, Any] = {
            "question": question,
            "item_id": item_id,
            "config_name": self.config_name,
            "answer_text": generated["answer_text"],
            "abstained": bool(generated["abstained"]),
            "abstain_reason": str(generated.get("abstain_reason") or ""),
            "claims": claims,
            "verified_claims": sum(1 for claim in claims if claim["verified"]),
            "retrieved": [self._hit_view(hit) for hit in shown],
            "retrieved_total": len(hits),
            "retrieval_ms": round(retrieval_ms, 1),
            "generation_ms": round(generation_ms, 1),
            "hops": hop_meta["hops"],
            "hop_stop_reason": hop_meta["stop_reason"],
            "best_chunk": self._hit_view(hits[0]) if hits else None,
        }
        response["insufficiency"] = self._insufficiency(response)
        return response

    def _hit_view(self, hit: Dict[str, Any]) -> Dict[str, Any]:
        chunk = self.chunks_by_id.get(hit["chunk_id"], {})
        doc = self.docs_by_id.get(hit["doc_id"], {})
        return {
            "chunk_id": hit["chunk_id"],
            "doc_id": hit["doc_id"],
            "rank": hit["rank"],
            "score": round(float(hit["score"]), 6),
            "doc_title": doc.get("title", ""),
            "heading_path": chunk.get("heading_path", ""),
            "url": doc.get("url", ""),
            "text": chunk.get("text", ""),
        }

    def _claim_views(
        self, claims: List[Dict[str, Any]], verdicts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Claims joined to their verdict, their chunk and their document.

        Numbering runs over verified claims only: a marker the reader can click
        must open a span that exists in a chunk that was actually retrieved.
        """
        views: List[Dict[str, Any]] = []
        number = 0
        for claim, verdict in zip(claims, verdicts):
            chunk = self.chunks_by_id.get(claim["chunk_id"], {})
            doc = self.docs_by_id.get(claim.get("doc_id") or chunk.get("doc_id", ""), {})
            verified = bool(verdict["supported"])
            if verified:
                number += 1
            start = verdict.get("span_start")
            end = verdict.get("span_end")
            span_text = ""
            if verified and start is not None and end is not None:
                span_text = chunk.get("text", "")[start:end]
            views.append(
                {
                    "claim_id": claim.get("claim_id", ""),
                    "text": claim.get("text", ""),
                    "quote": claim.get("quote", ""),
                    "verified": verified,
                    "error_class": verdict["error_class"],
                    "detail": verdict["detail"],
                    "span_start": start,
                    "span_end": end,
                    "span_text": span_text,
                    "chunk_id": claim["chunk_id"],
                    "doc_id": doc.get("doc_id", chunk.get("doc_id", "")),
                    "doc_title": doc.get("title", ""),
                    "heading_path": chunk.get("heading_path", ""),
                    "url": doc.get("url", ""),
                    "marker_number": number if verified else 0,
                    "marker": f"[{number}]" if verified else "",
                }
            )
        return views

    def _insufficiency(self, response: Dict[str, Any]) -> str:
        """One line on why the answer was withheld, in the reader's terms."""
        if not response["abstained"]:
            return ""
        best = response["best_chunk"]
        if best is None:
            return "Retrieval returned no chunk at all for this question."
        if best["score"] < self.threshold:
            return (
                f"The best chunk scored {best['score']:.3f}, below this "
                f"configuration's abstain threshold of {self.threshold:.3f}."
            )
        reason = response["abstain_reason"] or "no claim could be grounded"
        return (
            f"The best chunk scored {best['score']:.3f}, above the abstain threshold "
            f"of {self.threshold:.3f}, but the generator returned no claim it could "
            f"support from it ({reason})."
        )

    # ---- the citation a marker opens --------------------------------------
    def citation_payload(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """What travels with a citation marker's click.

        Small and JSON-safe on purpose: the panel is rebuilt from the chunk store
        when the click arrives, so a marker never carries a stale copy of the text.
        """
        if not claim.get("verified") or claim.get("span_start") is None:
            raise ValueError(
                "an unverified claim has no span to open "
                f"({claim.get('error_class') or 'not verified'})"
            )
        return {
            "marker": claim["marker"],
            "claim_id": claim["claim_id"],
            "claim_text": claim["text"],
            "chunk_id": claim["chunk_id"],
            "doc_id": claim["doc_id"],
            "span_start": claim["span_start"],
            "span_end": claim["span_end"],
        }

    def citation_props(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """The source panel: document title, heading path, URL, marked chunk text."""
        chunk_id = str(payload.get("chunk_id") or "")
        chunk = self.chunks_by_id.get(chunk_id)
        if chunk is None:
            raise KeyError(f"citation names a chunk that is not in this index: {chunk_id}")
        doc = self.docs_by_id.get(chunk["doc_id"], {})
        text = chunk["text"]
        start = payload.get("span_start")
        end = payload.get("span_end")
        if not isinstance(start, int) or not isinstance(end, int) or not (
            0 <= start < end <= len(text)
        ):
            raise ValueError(f"citation span is not inside chunk {chunk_id}")
        return {
            "marker": str(payload.get("marker") or ""),
            "claim": str(payload.get("claim_text") or ""),
            "doc_title": doc.get("title", ""),
            "heading_path": chunk.get("heading_path", ""),
            "url": doc.get("url", ""),
            "chunk_id": chunk_id,
            "doc_id": doc.get("doc_id", chunk["doc_id"]),
            "span_text": text[start:end],
            "chunk_html": (
                html.escape(text[:start])
                + "<mark>"
                + html.escape(text[start:end])
                + "</mark>"
                + html.escape(text[end:])
            ),
        }

    def describe(self) -> str:
        """The one-line statement of what this process is serving."""
        return (
            f"**Configuration `{self.config_name}`** - snapshot `{self.snapshot_id}`, "
            f"{self.chunk_count} chunks, `{self.cfg['chunk.strategy']}` chunking, "
            f"`{self.cfg['retrieval.mode']}` retrieval (k={self.k}), "
            f"embeddings `{self.embedder.model_id}`, generator "
            f"`{getattr(self.generator, 'model_id', 'unknown')}`, index "
            f"`{self.index_backend}`. Loaded once in "
            f"{self.build_seconds:.1f}s. Ask a question; every claim comes with a "
            f"citation you can open, and a question the corpus cannot answer is "
            f"abstained with the best chunk shown."
        )

    def close(self) -> None:
        for handle in (self.store, self.sparse, self.embedder, self.generator):
            closer = getattr(handle, "close", None)
            if callable(closer):
                closer()


_ENGINE: Optional[ChatEngine] = None
_HISTORY: Optional[object] = None
_HISTORY_ENV = "RAGQA_DEMO_HISTORY"
DEFAULT_HISTORY = "data/demo/history.sqlite"


def install_engine(engine: ChatEngine) -> ChatEngine:
    """Publish the engine built at process start, before Chainlit serves requests."""
    global _ENGINE
    _ENGINE = engine
    return engine


def get_engine() -> ChatEngine:
    """The process engine: built on first use if nothing was installed."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ChatEngine.from_config(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))
    return _ENGINE


def get_history(path: Optional[str] = None):
    """The process conversation store, so every tab shares one history file.

    Built in the main thread and used from Chainlit's worker threads, which is why
    `ConversationStore` opens its connection with `check_same_thread=False` and guards
    every statement behind a lock — the same class of bug that made the stateless demo
    hang on its first real question.
    """
    global _HISTORY
    if _HISTORY is None:
        from .history import ConversationStore

        _HISTORY = ConversationStore(path or os.environ.get(_HISTORY_ENV, DEFAULT_HISTORY))
    return _HISTORY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ragqa.demo", description="Serve one configuration as a chat demo."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to a YAML configuration")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """`python -m ragqa serve --config <path>`: load the pipeline once, then serve."""
    args = build_parser().parse_args(argv)
    os.environ[CONFIG_ENV] = os.path.abspath(args.config)

    engine = install_engine(ChatEngine.from_config(args.config))
    print(
        f"demo: configuration {engine.config_name!r} "
        f"({engine.chunk_count} chunks, {engine.index_backend} index, "
        f"generator {getattr(engine.generator, 'model_id', '?')}) "
        f"loaded in {engine.build_seconds:.1f}s"
    )
    print(f"demo: serving http://127.0.0.1:{os.environ.get('CHAINLIT_PORT', '8000')}")

    from chainlit.cli import run_chainlit

    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chainlit_app.py")
    run_chainlit(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
