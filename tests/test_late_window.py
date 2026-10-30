from __future__ import annotations

from types import SimpleNamespace

from ragqa.embed import LateChunkingEmbedder


def _geometry(window_tokens=2048, window_overlap=256, max_seq_length=8192):
    return SimpleNamespace(
        window_tokens=window_tokens,
        window_overlap=window_overlap,
        max_seq_length=max_seq_length,
    )


def test_a_short_document_is_one_window():
    windows = LateChunkingEmbedder.windows_for(_geometry(), 500)
    assert windows == [(0, 500)]


def test_a_long_document_is_covered_without_gaps():
    windows = LateChunkingEmbedder.windows_for(_geometry(), 10_000)
    assert windows[0][0] == 0
    assert windows[-1][1] == 10_000
    for previous, following in zip(windows, windows[1:]):
        assert following[0] < previous[1], "windows must overlap"
        assert following[0] > previous[0], "windows must advance"


def test_window_never_exceeds_the_configured_size():
    windows = LateChunkingEmbedder.windows_for(_geometry(), 10_000)
    assert all(end - start <= 2048 for start, end in windows)


def test_overlap_is_clamped_so_the_window_always_advances():
    windows = LateChunkingEmbedder.windows_for(
        _geometry(window_tokens=100, window_overlap=999), 400
    )
    assert len(windows) > 1
    assert all(start < end for start, end in windows)
    assert windows[-1][1] == 400


def test_an_empty_document_still_returns_one_window():
    assert LateChunkingEmbedder.windows_for(_geometry(), 0) == [(0, 0)]
