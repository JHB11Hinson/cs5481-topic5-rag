"""The error taxonomy note and its machine-readable companion cannot drift (ticket 15).

`notes/error-taxonomy.md` is the prose a reader of the report checks, and
`notes/error-taxonomy.json` is the same numbers in a form the report bundle can
load. Two files carrying one table is exactly the shape that drifts: a row gets
recounted in the note and the JSON keeps the old number, or a tenth class is added
on one side only. These tests read both files the way the report does -- the note's
markdown tables and the JSON tree -- and fail when they disagree.

Nothing here re-derives the classification from the run directories: that needs a
chunk rebuild and 60 golden items per cell, and it belongs to the note's own
extraction step, not to a unit test.
"""

from __future__ import annotations

import json
import os
import re

import pytest

NOTE_MD = os.path.join("notes", "error-taxonomy.md")
NOTE_JSON = os.path.join("notes", "error-taxonomy.json")

#: The nine classes were fixed before the runs were inspected. A tenth is a
#: decision for the note to argue in prose, so it must be added here deliberately.
FIXED_CLASSES = [
    "retrieval-document-miss",
    "retrieval-chunk-miss",
    "context-budget-drop",
    "generator-over-abstention",
    "generator-under-abstention",
    "citation-quote-not-in-chunk",
    "citation-span-out-of-bounds",
    "citation-chunk-not-retrieved",
    "generation-parse-failure",
]

SAMPLE_TARGET = 40


def _load():
    with open(NOTE_JSON, encoding="utf-8") as handle:
        return json.load(handle)


def _md_text():
    with open(NOTE_MD, encoding="utf-8") as handle:
        return handle.read()


def _table_after(text, caption):
    """Rows of the first markdown table whose caption line contains `caption`."""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if caption in line and not line.startswith("|")),
        None,
    )
    assert start is not None, f"no caption line mentioning {caption!r} in {NOTE_MD}"
    rows = []
    for line in lines[start:]:
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    assert rows, f"no table under the caption mentioning {caption!r}"
    return rows


def _count_table():
    """`{class: {cell: n}}`, with the `total` row and column kept under those keys."""
    rows = _table_after(_md_text(), "Counts per class per cell")
    header = [cell.strip("`") for cell in rows[0]]
    assert header[0] == "class", f"first column is {header[0]!r}, expected the class name"
    assert header[-1] == "total", f"last column is {header[-1]!r}, expected the row total"
    columns = header[1:]
    table = {}
    for row in rows[1:]:
        if set("".join(row)) <= {"-", ":", " "}:
            continue
        values = {}
        for index, name in enumerate(columns, start=1):
            values[name] = int(row[index].replace("*", "").strip())
        table[row[0].strip("`* ")] = values
    return columns, table


def _sample_rows():
    rows = _table_after(_md_text(), "The forty failures")
    header = [cell.strip("`") for cell in rows[0]]
    body = []
    for row in rows[1:]:
        if set("".join(row)) <= {"-", ":", " "}:
            continue
        body.append(dict(zip(header, row)))
    return header, body


def test_note_files_exist():
    assert os.path.isfile(NOTE_MD)
    assert os.path.isfile(NOTE_JSON)


def test_json_declares_exactly_the_nine_fixed_classes():
    payload = _load()
    names = [entry["name"] for entry in payload["classes"]]
    assert names == FIXED_CLASSES


def test_markdown_table_rows_are_the_same_nine_classes():
    columns, table = _count_table()
    assert list(table) == FIXED_CLASSES + ["total"]
    assert columns == _load()["cells"] + ["total"]


def test_every_cell_row_in_the_note_matches_the_json():
    columns, table = _count_table()
    payload = _load()
    counts = payload["counts"]
    for cell in payload["cells"]:
        assert cell in columns, f"{cell} is in the JSON but has no column in {NOTE_MD}"
        for name in FIXED_CLASSES:
            assert table[name][cell] == counts[cell][name], (
                f"{cell} / {name}: note says {table[name][cell]}, "
                f"json says {counts[cell][name]}"
            )
    assert set(columns) == set(payload["cells"]) | {"total"}, (
        "the note's columns and the JSON's cells disagree: "
        f"{sorted(set(columns) ^ (set(payload['cells']) | {'total'}))}"
    )


def test_column_and_row_totals_add_up_in_both_files():
    columns, table = _count_table()
    payload = _load()
    for name in FIXED_CLASSES:
        printed = table[name]["total"]
        assert printed == sum(table[name][cell] for cell in payload["cells"])
        assert printed == payload["totals"][name]
    for cell in payload["cells"]:
        printed = table["total"][cell]
        assert printed == sum(table[name][cell] for name in FIXED_CLASSES)
        assert printed == sum(payload["counts"][cell].values())
    assert table["total"]["total"] == sum(payload["totals"].values())


def test_totals_match_the_sample_bookkeeping():
    payload = _load()
    assert len(payload["sample"]) == SAMPLE_TARGET
    assert payload["sampling"]["target"] == SAMPLE_TARGET


def test_the_note_prints_the_same_forty_rows_as_the_json():
    _, body = _sample_rows()
    payload = _load()
    assert len(body) == SAMPLE_TARGET
    for index, row in enumerate(body):
        entry = payload["sample"][index]
        assert row["run id"].strip("`") == entry["run_id"], f"row {index + 1} run id"
        assert row["item"].strip("`") == entry["item_id"], f"row {index + 1} item"
        assert row["class"].strip("`") == entry["class"], f"row {index + 1} class"
        assert len(row["justification"]) > 40, f"row {index + 1} has no usable justification"


def test_every_sampled_class_is_one_of_the_nine_and_occurs_in_the_counts():
    payload = _load()
    _, table = _count_table()
    for entry in payload["sample"]:
        assert entry["class"] in FIXED_CLASSES
        assert entry["cell"] in payload["counts"]
        assert table[entry["class"]][entry["cell"]] >= 1, (
            f"sample says {entry['cell']} / {entry['class']} but the note counts zero there"
        )


def test_sample_is_spread_across_classes_and_cells():
    payload = _load()
    sampled_classes = {entry["class"] for entry in payload["sample"]}
    sampled_cells = {entry["cell"] for entry in payload["sample"]}
    assert len(sampled_classes) >= 6, f"only {len(sampled_classes)} classes inspected"
    assert len(sampled_cells) >= 12, f"only {len(sampled_cells)} cells inspected"


def test_classes_that_never_fire_are_named_as_such():
    text = _md_text()
    payload = _load()
    silent = [name for name, total in payload["totals"].items() if total == 0]
    assert silent, "expected at least one class to be empty across eighteen cells"
    for name in silent:
        windows = [m.group(0) for m in re.finditer(re.escape(name) + r".{0,300}", text, re.S)]
        assert windows, f"{name} never appears in {NOTE_MD}"
        assert any("never fire" in window for window in windows), (
            f"{name} has a zero total but the note never says it never fires"
        )
