"""Chunk strategies.

Two strategies live here because they are two levels of one experimental factor
(`ADR-0006`): a fixed word window with overlap, and a recursive splitter that
respects headings before paragraphs before sentences and then groups children
under a parent. Chunk ids are content-addressed so they are stable across
processes and machines.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

from .textutil import normalize, sentence_spans, word_count, word_spans

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
MIN_TEXT_CHARS = 1
# Atomic units (tables, code) are kept whole until this many words, then split on
# line boundaries. A 2,000-word table padded inside a batch is what turns a 6 GB
# card into an out-of-memory error: attention is quadratic in sequence length.
ATOMIC_CAP = 1024


def chunk_id(doc_id: str, start: int, end: int, text: str) -> str:
    """Content-addressed id: same inputs, same id, on any machine."""
    digest = hashlib.sha1(
        f"{doc_id}|{start}|{end}|{normalize(text)}".encode("utf-8")
    ).hexdigest()[:16]
    return f"c-{digest}"


def _make(
    doc: Dict[str, Any],
    kind: str,
    heading_path: str,
    start: int,
    end: int,
    text: str,
    parent_id: str = "",
) -> Dict[str, Any]:
    return {
        "chunk_id": chunk_id(doc["doc_id"], start, end, text),
        "doc_id": doc["doc_id"],
        "kind": kind,
        "heading_path": heading_path,
        "text": text,
        "char_start": start,
        "char_end": end,
        "token_count": word_count(text),
        "parent_id": parent_id,
    }


def chunk_fixed(doc: Dict[str, Any], size: int, overlap: int) -> List[Dict[str, Any]]:
    """Sliding word window. Boundaries ignore syntax entirely — that is the point."""
    spans = word_spans(doc["text"])
    if not spans:
        return []
    step = max(1, size - overlap)
    chunks: List[Dict[str, Any]] = []
    i = 0
    while i < len(spans):
        window = spans[i : i + size]
        start, end = window[0][1], window[-1][2]
        text = doc["text"][start:end]
        if len(text) >= MIN_TEXT_CHARS:
            chunks.append(
                _make(doc, "child", doc.get("heading_path", ""), start, end, text)
            )
        if i + size >= len(spans):
            break
        i += step
    return chunks


def _sections(text: str) -> List[Tuple[str, int, int]]:
    """Heading path, body start, body end — one entry per markdown section."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [("", 0, len(text))]
    sections: List[Tuple[str, int, int]] = []
    stack: List[Tuple[int, str]] = []
    cursor = 0
    for idx, match in enumerate(matches):
        if idx == 0 and match.start() > 0:
            sections.append(("", 0, match.start()))
        level = len(match.group(1))
        title = match.group(2).strip()
        stack = [(lv, name) for lv, name in stack if lv < level]
        stack.append((level, title))
        heading_path = " > ".join(name for _, name in stack)
        body_start = match.end()
        body_end = (
            matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        )
        sections.append((heading_path, body_start, body_end))
        cursor = body_end
    return sections


def _split_long(sentence: str, start: int, size: int) -> List[Tuple[str, int, int]]:
    """A single sentence longer than `size` gets hard-split on word boundaries."""
    spans = word_spans(sentence)
    parts: List[Tuple[str, int, int]] = []
    i = 0
    while i < len(spans):
        window = spans[i : i + size]
        piece_start = start + window[0][1]
        piece_end = start + window[-1][2]
        parts.append((sentence[window[0][1] : window[-1][2]], piece_start, piece_end))
        if i + size >= len(spans):
            break
        i += size
    return parts


_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^\s*```")
TABLE_LINE = re.compile(r"^\s*\|")


def _units(text: str) -> List[Tuple[str, int, int, str, bool]]:
    """(text, start, end, heading_path, atomic) in document order.

    Atomic units — fenced code and tables — are never cut by the sentence
    machinery: keeping a table intact is the whole hypothesis behind this
    strategy, and it is what the fixed window cannot do (ADR-0010).
    """
    units: List[Tuple[str, int, int, str, bool]] = []
    stack: List[Tuple[int, str]] = []
    lines = text.splitlines(keepends=True)
    offsets: List[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)

    index = 0
    total = len(lines)
    while index < total:
        raw = lines[index]
        base = offsets[index]
        line = raw.rstrip("\r\n")

        heading = _HEADING_LINE.match(line)
        if heading:
            level = len(heading.group(1))
            stack = [(lv, name) for lv, name in stack if lv < level]
            stack.append((level, heading.group(2).strip()))
            index += 1
            continue

        heading_path = " > ".join(name for _, name in stack)

        if FENCE.match(line):
            end_index = index + 1
            block = [raw]
            while end_index < total and not FENCE.match(lines[end_index].rstrip("\r\n")):
                block.append(lines[end_index])
                end_index += 1
            if end_index < total:
                block.append(lines[end_index])
                end_index += 1
            body = "".join(block)
            units.append((body.strip("\n"), base, base + len(body), heading_path, True))
            index = end_index
            continue

        if TABLE_LINE.match(line):
            end_index = index
            block = []
            while end_index < total and TABLE_LINE.match(lines[end_index].rstrip("\r\n")):
                block.append(lines[end_index])
                end_index += 1
            body = "".join(block)
            units.append((body.strip("\n"), base, base + len(body), heading_path, True))
            index = end_index
            continue

        end_index = index
        paragraph = []
        while end_index < total:
            candidate = lines[end_index].rstrip("\r\n")
            if not candidate.strip():
                break
            if FENCE.match(candidate) or TABLE_LINE.match(candidate) or _HEADING_LINE.match(candidate):
                break
            paragraph.append(lines[end_index])
            end_index += 1
        if not paragraph:
            index += 1
            continue
        body = "".join(paragraph)
        for sentence, start, end in sentence_spans(body):
            units.append((sentence, base + start, base + end, heading_path, False))
        index = end_index
    return units


def _split_lines(text: str, start: int, cap: int) -> List[Tuple[str, int, int]]:
    """Split an over-large atomic unit on line boundaries, keeping lines whole."""
    parts: List[Tuple[str, int, int]] = []
    buffer: List[str] = []
    buffer_words = 0
    offset = 0
    piece_start = 0
    for raw in text.splitlines(keepends=True):
        count = word_count(raw)
        if buffer and buffer_words + count > cap:
            body = "".join(buffer)
            parts.append((body.strip("\n"), start + piece_start, start + offset))
            buffer = []
            buffer_words = 0
            piece_start = offset
        buffer.append(raw)
        buffer_words += count
        offset += len(raw)
    if buffer:
        body = "".join(buffer)
        parts.append((body.strip("\n"), start + piece_start, start + offset))
    return parts


def chunk_recursive(
    doc: Dict[str, Any], size: int, parent_size: int
) -> List[Dict[str, Any]]:
    """Accumulate units to a word budget; parents are consecutive groups (ADR-0010)."""
    children: List[Dict[str, Any]] = []
    buffer: List[Tuple[str, int, int]] = []
    buffer_words = 0
    buffer_heading = ""

    def flush() -> None:
        nonlocal buffer, buffer_words, buffer_heading
        if not buffer:
            return
        start, end = buffer[0][1], buffer[-1][2]
        text = doc["text"][start:end]
        if len(text) >= MIN_TEXT_CHARS:
            children.append(_make(doc, "child", buffer_heading, start, end, text))
        buffer = []
        buffer_words = 0
        buffer_heading = ""

    for text, start, end, heading_path, atomic in _units(doc["text"]):
        count = word_count(text)
        if count == 0:
            continue
        if count > size:
            flush()
            if not atomic:
                for piece, p_start, p_end in _split_long(text, start, size):
                    children.append(_make(doc, "child", heading_path, p_start, p_end, piece))
            elif count > ATOMIC_CAP:
                for piece, p_start, p_end in _split_lines(text, start, ATOMIC_CAP):
                    if word_count(piece):
                        children.append(_make(doc, "child", heading_path, p_start, p_end, piece))
            else:
                children.append(_make(doc, "child", heading_path, start, end, text))
            continue
        if buffer and buffer_words + count > size:
            flush()
        if not buffer:
            buffer_heading = heading_path
        buffer.append((text, start, end))
        buffer_words += count
    flush()

    parents = _build_parents(doc, children, parent_size)
    by_id = {p["chunk_id"]: p for p in parents}
    for child in children:
        owner = child.get("_parent_key")
        if owner and owner in by_id:
            child["parent_id"] = owner
        child.pop("_parent_key", None)
    return children + parents


def _build_parents(
    doc: Dict[str, Any], children: List[Dict[str, Any]], parent_size: int
) -> List[Dict[str, Any]]:
    """Group consecutive children within the document until the parent budget fills."""
    parents: List[Dict[str, Any]] = []
    group: List[Dict[str, Any]] = []

    def flush() -> None:
        nonlocal group
        if not group:
            return
        start = group[0]["char_start"]
        end = group[-1]["char_end"]
        parent = _make(doc, "parent", group[0]["heading_path"], start, end, doc["text"][start:end])
        parents.append(parent)
        for child in group:
            child["_parent_key"] = parent["chunk_id"]
        group = []

    for child in children:
        if group and group[-1]["token_count"] + child["token_count"] > parent_size:
            flush()
        group.append(child)
    flush()
    return parents


def build(docs: List[Dict[str, Any]], strategy: str, size: int, overlap: int, parent_size: int) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for doc in docs:
        if strategy == "fixed":
            chunks.extend(chunk_fixed(doc, size, overlap))
        elif strategy == "recursive_parent_child":
            chunks.extend(chunk_recursive(doc, size, parent_size))
        else:
            raise ValueError(f"unknown chunk strategy {strategy!r}")
    return chunks


def _percentile(values: List[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return int(ordered[int(round(fraction * (len(ordered) - 1)))])


def chunk_set_id(snapshot_id: str, strategy: str, size: int, overlap: int, parent_size: int) -> str:
    if strategy == "fixed":
        return f"{snapshot_id}-fixed-{size}-o{overlap}"
    return f"{snapshot_id}-{strategy}-{size}-p{parent_size}"


def main(argv: List[str] = None) -> int:
    """Build chunk sets for one corpus snapshot: `python -m ragqa.chunk --config ...`."""
    import argparse
    import json
    import os

    from . import config as config_mod
    from .corpus import load_documents

    parser = argparse.ArgumentParser(prog="ragqa.chunk", description="Build chunk sets.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--strategy", default="both",
                        choices=["fixed", "recursive_parent_child", "both"])
    parser.add_argument("--out", default="data/chunks")
    args = parser.parse_args(argv)

    cfg = config_mod.load(args.config)
    docs = load_documents(cfg["corpus.source"])
    print(f"documents: {len(docs)}")

    wanted = (
        ["fixed", "recursive_parent_child"] if args.strategy == "both" else [args.strategy]
    )
    for strategy in wanted:
        chunks = build(
            docs,
            strategy,
            int(cfg["chunk.size"]),
            int(cfg["chunk.overlap"]),
            int(cfg["chunk.parent_size"]),
        )
        set_id = chunk_set_id(
            cfg["corpus.snapshot_id"], strategy,
            int(cfg["chunk.size"]), int(cfg["chunk.overlap"]), int(cfg["chunk.parent_size"]),
        )
        out_dir = os.path.join(args.out, set_id)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "chunks.jsonl"), "w", encoding="utf-8", newline="\n") as handle:
            for row in chunks:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        summary = stats(chunks, int(cfg["chunk.size"]))
        summary["chunk_set_id"] = set_id
        summary["strategy"] = strategy
        summary["corpus_snapshot"] = cfg["corpus.snapshot_id"]
        summary["parameters"] = {
            "size": int(cfg["chunk.size"]),
            "overlap": int(cfg["chunk.overlap"]),
            "parent_size": int(cfg["chunk.parent_size"]),
            "unit": "whitespace words (token proxy until ticket 04 re-tokenises)",
        }
        with open(os.path.join(out_dir, "chunk_stats.json"), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(
            "{}: chunks={} parents={} mean={} p95={} mid_sentence={} table={}".format(
                strategy,
                summary["chunks"],
                summary["parents"],
                summary["mean_tokens"],
                summary["p95_tokens"],
                summary["share_ending_mid_sentence"],
                summary["share_containing_table_row"],
            )
        )
        print(f"  -> {out_dir}")
    return 0


def stats(chunks: List[Dict[str, Any]], size: int = 0) -> Dict[str, Any]:
    children = [c for c in chunks if c["kind"] == "child"]
    parents = [c for c in chunks if c["kind"] == "parent"]
    counts = sorted(c["token_count"] for c in children)
    prose = [
        c for c in children
        if "|" not in c["text"] and "```" not in c["text"]
    ]
    mid_sentence = sum(1 for c in prose if c["text"].strip()[-1:] not in ".!?:`\"'")
    table_hit = sum(1 for c in children if "|" in c["text"])
    fence_hit = sum(1 for c in children if "```" in c["text"])
    return {
        "chunks": len(children),
        "parents": len(parents),
        "mean_tokens": round(sum(counts) / len(counts), 2) if counts else 0.0,
        "p50_tokens": _percentile(counts, 0.5),
        "p95_tokens": _percentile(counts, 0.95),
        "share_ending_mid_sentence": round(mid_sentence / len(prose), 4) if prose else 0.0,
        "share_containing_table_row": round(table_hit / len(children), 4) if children else 0.0,
        "share_containing_code_fence": round(fence_hit / len(children), 4) if children else 0.0,
        "share_over_budget": round(
            sum(1 for c in children if c["token_count"] > size) / len(children), 4
        ) if (children and size) else 0.0,
    }


if __name__ == "__main__":
    raise SystemExit(main())
