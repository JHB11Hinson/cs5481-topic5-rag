"""Small text utilities shared by chunking, generation and evaluation.

Whitespace-word counts stand in for tokens until the real embedding tokenizer
lands (ticket 04). Every function here is deterministic and pure.
"""

from __future__ import annotations

import re
from typing import List, Tuple

_WS = re.compile(r"\s+")
_WORD = re.compile(r"\S+")
_SENT = re.compile(r"[^.!?]*[.!?]+")
_ALNUM = re.compile(r"[a-z0-9_]+")


def normalize(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip the ends."""
    return _WS.sub(" ", text or "").strip()


def words(text: str) -> List[str]:
    return _WORD.findall(text or "")


def word_count(text: str) -> int:
    return len(words(text))


def word_spans(text: str) -> List[Tuple[str, int, int]]:
    """Word, start offset, end offset — offsets are into `text` as given."""
    return [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(text or "")]


def sentence_spans(text: str) -> List[Tuple[str, int, int]]:
    """Sentence, start offset, end offset.

    A trailing fragment without terminal punctuation is included, so no text is
    ever silently dropped between sentences.
    """
    spans: List[Tuple[str, int, int]] = []
    consumed = 0
    for m in _SENT.finditer(text or ""):
        raw = m.group(0)
        stripped = raw.strip()
        if stripped:
            lead = len(raw) - len(raw.lstrip())
            start = m.start() + lead
            spans.append((stripped, start, start + len(stripped)))
        consumed = m.end()
    tail = (text or "")[consumed:]
    if tail.strip():
        lead = len(tail) - len(tail.lstrip())
        start = consumed + lead
        spans.append((tail.strip(), start, start + len(tail.strip())))
    return spans


def token_set(text: str) -> set:
    return set(_ALNUM.findall((text or "").lower()))


def overlap_ratio(a: str, b: str) -> float:
    """Share of `a`'s tokens that also occur in `b`, in [0, 1]."""
    ta, tb = token_set(a), token_set(b)
    if not ta:
        return 0.0
    return len(ta & tb) / float(len(ta))


def locate_normalized(text: str, quote: str) -> Tuple[int, int]:
    """Char span of `quote` inside `text`, tolerating whitespace differences.

    Returns (-1, -1) when the quote is not present. A model quoting a passage
    cannot be trusted to preserve its line breaks, and offsets are what the
    verifier checks, so the mapping back to original offsets has to be computed
    rather than taken from the model.
    """
    target = normalize(quote)
    if not target:
        return (-1, -1)
    builder: List[str] = []
    mapping: List[int] = []
    previous_space = False
    for index, char in enumerate(text or ""):
        if char.isspace():
            if previous_space:
                continue
            builder.append(" ")
            mapping.append(index)
            previous_space = True
        else:
            builder.append(char)
            mapping.append(index)
            previous_space = False
    normalized = "".join(builder)
    position = normalized.find(target)
    if position < 0:
        return (-1, -1)
    start = mapping[position]
    end = mapping[position + len(target) - 1] + 1
    return (start, end)
