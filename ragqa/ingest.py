"""Corpus ingest: fetch one pinned documentation tree and parse it twice.

Two variants come out of one source (ADR-0007): structure-aware text where
headings, tables and fenced code survive, and stripped plain text where they do
not. The difference is an experiment, so neither variant may recover the other's
information.

Include handling follows ADR-0009: a fragment used by one page is inlined, a
fragment used by several is indexed once and referenced by marker.

Usage:
    python -m ragqa.ingest --ref <sha> [--clone URL]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

from .corpus import content_hash
from .textutil import normalize

PRODUCT = "vault"
DOC_DIRS = ("content/docs", "content/api-docs")
PARTIALS_DIR = "content/partials"

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
INCLUDE = re.compile(r"^@include\s+'([^']+)'\s*$", re.M)
IMPORT_LINE = re.compile(r"^\s*import\s+.+$", re.M)
TAB_OPEN = re.compile(r"<Tab\b([^>]*)>")
ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
HTML_TABLE = re.compile(r"<table\b.*?</table>", re.S)
TABLE_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
TABLE_CELL = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.S)
ALERT = re.compile(r"<(Note|Tip|Warning)\b([^>]*)>")
TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9.]*[^>]*>")
BLANK_RUN = re.compile(r"\n{3,}")


def _frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.strip().startswith("#"):
            key, value = line.split(":", 1)
            value = value.strip().lstrip(">-").strip()
            if value:
                meta[key.strip()] = value
    return meta, text[match.end():]


class Roots:
    """Where an include may live, in the order the site build would look."""

    def __init__(self, repo_root: str, product_root: str):
        self.repo = repo_root
        self.product = product_root
        self.content = os.path.join(product_root, "content")
        self.repo_content = os.path.join(repo_root, "content")

    def candidates(self, spec: str, source: str) -> List[str]:
        relative = spec.lstrip("/")
        options = [
            os.path.normpath(os.path.join(os.path.dirname(source), spec)),
            os.path.normpath(os.path.join(self.content, "partials", relative)),
            os.path.normpath(os.path.join(self.content, relative)),
        ]
        if "/global/" in spec:
            tail = spec.split("/global/", 1)[1]
            options.append(os.path.normpath(os.path.join(self.repo_content, "global", tail)))
            options.append(os.path.normpath(os.path.join(self.content, "partials", tail)))
        return options

    def resolve(self, spec: str, source: str) -> Optional[str]:
        for candidate in self.candidates(spec, source):
            if os.path.isfile(candidate):
                return candidate
        return None


def partial_doc_id(path: str, content_root: str) -> str:
    rel = os.path.relpath(path, content_root).replace(os.sep, "/")
    if rel.endswith(".mdx"):
        rel = rel[: -len(".mdx")]
    if rel.endswith("/index"):
        rel = rel[: -len("/index")]
    return f"partials/{rel}" if not rel.startswith("partials/") else rel


def _html_table_to_pipe(block: str) -> str:
    rows: List[str] = []
    for row_html in TABLE_ROW.findall(block):
        cells = [normalize(TAG.sub("", cell)) for cell in TABLE_CELL.findall(row_html)]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _attributes(block: str) -> Dict[str, str]:
    return {key: value for key, value in ATTR.findall(block)}


def parse_mdx(
    text: str,
    source: str = "",
    roots: Optional[Roots] = None,
    plan: Optional[Dict[str, str]] = None,
    stats: Optional[Dict[str, int]] = None,
    depth: int = 0,
) -> Tuple[Dict[str, str], str]:
    """MDX → (metadata, structured text). Include handling follows `plan`."""
    if stats is None:
        stats = {"inlined": 0, "marked": 0, "missing": 0}
    if plan is None:
        plan = {}
    if depth > 3:
        return {}, text

    meta, body = _frontmatter(text)

    def replace_include(match: "re.Match") -> str:
        spec = match.group(1)
        target = roots.resolve(spec, source) if roots else None
        if target is None:
            stats["missing"] += 1
            return ""
        action = plan.get(target, "marker")
        if action == "inline" and depth == 0:
            stats["inlined"] += 1
            with open(target, "r", encoding="utf-8", errors="replace") as handle:
                _, child_body = parse_mdx(handle.read(), target, roots, plan, stats, depth + 1)
            return child_body
        stats["marked"] += 1
        return f"\n[shared partial: {partial_doc_id(target, roots.content)}]\n"

    body = INCLUDE.sub(replace_include, body)
    body = IMPORT_LINE.sub("", body)
    body = TAB_OPEN.sub(
        lambda m: "\n#### " + _attributes(m.group(1)).get("heading", "More") + "\n", body
    )
    body = body.replace("</Tab>", "\n")

    def replace_alert(match: "re.Match") -> str:
        kind = match.group(1)
        title = _attributes(match.group(2)).get("title", "")
        label = f"{kind}: {title}" if title else kind
        return f"\n> {label}\n"

    body = ALERT.sub(replace_alert, body)
    for closing in ("</Note>", "</Tip>", "</Warning>"):
        body = body.replace(closing, "")
    body = body.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    body = HTML_TABLE.sub(lambda m: _html_table_to_pipe(m.group(0)), body)
    body = TAG.sub("", body)
    body = BLANK_RUN.sub("\n\n", body).strip()
    return meta, body


def to_plain(structured: str) -> str:
    """Strip every structural marker. Table rows flatten, headings lose rank."""
    text = re.sub(r"^#{1,6}\s*", "", structured, flags=re.M)
    text = re.sub(r"^```[A-Za-z0-9_-]*\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.M)
    text = text.replace("|", " ")
    text = re.sub(r"[`*_]", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def doc_id_for(relative_path: str) -> str:
    path = relative_path.replace(os.sep, "/")
    if path.endswith(".mdx"):
        path = path[: -len(".mdx")]
    if path.endswith("/index"):
        path = path[: -len("/index")]
    return path


def url_for(doc_id: str) -> str:
    if doc_id.startswith("partials/"):
        return ""
    return f"https://developer.hashicorp.com/{PRODUCT}/{doc_id}"


def collect_pages(product_root: str) -> List[str]:
    pages: List[str] = []
    for directory in DOC_DIRS:
        base = os.path.join(product_root, directory)
        if not os.path.isdir(base):
            continue
        for current, _, files in os.walk(base):
            for name in files:
                if name.endswith(".mdx"):
                    pages.append(os.path.join(current, name))
    return sorted(pages)


def git_sha(path: str) -> str:
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def sparse_clone(url: str, ref: str, dest: str, product_path: str) -> str:
    """Blobless sparse checkout of one content tree; returns the resolved SHA."""
    if os.path.isdir(os.path.join(dest, ".git")):
        return git_sha(dest)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--sparse", "--depth", "1", url, dest],
        check=True,
    )
    subprocess.run(
        ["git", "-C", dest, "sparse-checkout", "set", product_path, "content/global"],
        check=True,
    )
    if ref and ref != "HEAD":
        subprocess.run(["git", "-C", dest, "fetch", "--depth", "1", "origin", ref], check=True)
        subprocess.run(["git", "-C", dest, "checkout", "FETCH_HEAD"], check=True)
    return git_sha(dest)


def plan_includes(
    pages: List[str], roots: Roots
) -> Tuple[Dict[str, str], Dict[str, List[str]], Dict[str, int]]:
    """Decide inline-versus-index-once for every referenced fragment (ADR-0009)."""
    references: Dict[str, List[str]] = {}
    unresolved: Dict[str, int] = {}
    for page in pages:
        with open(page, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        for spec in INCLUDE.findall(text):
            target = roots.resolve(spec, page)
            if target is None:
                unresolved[spec] = unresolved.get(spec, 0) + 1
                continue
            references.setdefault(target, []).append(page)
    plan = {target: ("inline" if len(pages_) == 1 else "marker") for target, pages_ in references.items()}
    return plan, references, unresolved


def ingest(
    source: str,
    product_path: str,
    snapshot_id: str,
    out_dir: str,
    ref: str = "",
) -> Dict[str, object]:
    product_root = os.path.join(source, product_path) if product_path else source
    content_root = os.path.join(product_root, "content")
    roots = Roots(source, product_root)
    pages = collect_pages(product_root)
    if not pages:
        raise SystemExit(f"no pages found under {content_root}")

    plan, references, unresolved = plan_includes(pages, roots)
    stats = {"inlined": 0, "marked": 0, "missing": 0}
    parse_failures: List[str] = []
    structured_rows: List[Dict[str, object]] = []
    plain_rows: List[Dict[str, object]] = []

    def emit(doc_id: str, title: str, description: str, url: str, rel: str, structured: str) -> None:
        structured_rows.append(
            {
                "doc_id": doc_id,
                "title": title,
                "description": description,
                "heading_path": title,
                "url": url,
                "source_path": rel,
                "text": structured,
            }
        )
        plain_rows.append(
            {
                "doc_id": doc_id,
                "title": title,
                "heading_path": title,
                "url": url,
                "source_path": rel,
                "text": to_plain(structured),
            }
        )

    for path in pages:
        rel = os.path.relpath(path, content_root).replace(os.sep, "/")
        doc_id = doc_id_for(rel)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                raw = handle.read()
            meta, structured = parse_mdx(raw, path, roots, plan, stats)
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            parse_failures.append(f"{rel}: {exc}")
            continue
        if not structured.strip():
            parse_failures.append(f"{rel}: parsed to empty text")
            continue
        title = meta.get("page_title") or doc_id.split("/")[-1].replace("-", " ").title()
        emit(doc_id, title, meta.get("description", ""), url_for(doc_id), rel, structured)

    shared = sorted(target for target, action in plan.items() if action == "marker")
    for path in shared:
        rel = os.path.relpath(path, content_root).replace(os.sep, "/")
        doc_id = partial_doc_id(path, content_root)
        referrers = references.get(path, [])
        first = referrers[0] if referrers else ""
        first_id = doc_id_for(os.path.relpath(first, content_root)) if first else ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                meta, structured = parse_mdx(handle.read(), path, roots, plan, stats, depth=1)
        except Exception as exc:  # noqa: BLE001
            parse_failures.append(f"{rel}: {exc}")
            continue
        if not structured.strip():
            parse_failures.append(f"{rel}: parsed to empty text")
            continue
        title = meta.get("page_title") or doc_id.split("/")[-1].replace("-", " ").title()
        emit(doc_id, title, meta.get("description", ""), url_for(first_id), rel, structured)

    os.makedirs(out_dir, exist_ok=True)
    for name, rows in (
        ("docs_structured.jsonl", structured_rows),
        ("docs_plain.jsonl", plain_rows),
    ):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    per_doc = sorted(
        (
            {
                "doc_id": row["doc_id"],
                "sha256": content_hash(str(row["text"])),
                "chars": len(str(row["text"])),
                "source_path": row["source_path"],
            }
            for row in structured_rows
        ),
        key=lambda item: item["doc_id"],
    )
    digest = hashlib.sha256(
        "".join(f"{d['doc_id']}:{d['sha256']}" for d in per_doc).encode("utf-8")
    ).hexdigest()

    manifest = {
        "snapshot_id": snapshot_id,
        "product": PRODUCT,
        "product_path": product_path,
        "repo_sha": ref or git_sha(source),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_versions": {"python": platform.python_version(), "ingest": "2"},
        "documents": len(structured_rows),
        "pages": len(pages),
        "fragment_documents": len(shared),
        "parse_failures": parse_failures,
        "structured_chars": sum(len(str(row["text"])) for row in structured_rows),
        "plain_chars": sum(len(str(row["text"])) for row in plain_rows),
        "includes": {
            "distinct_referenced": len(plan),
            "inlined": sum(1 for action in plan.values() if action == "inline"),
            "indexed_once": len(shared),
            "unresolved_references": sum(unresolved.values()),
            "unresolved_distinct": len(unresolved),
            "events": stats,
        },
        "digest": digest,
        "docs": per_doc,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return manifest


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="ragqa.ingest", description="Snapshot a docs tree.")
    parser.add_argument("--source", default="data/raw/web-unified-docs")
    parser.add_argument("--clone", default="", help="git URL to sparse-clone when --source is absent")
    parser.add_argument("--ref", default="", help="commit SHA to pin")
    parser.add_argument("--product-path", default="content/vault/v1.21.x")
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    if args.clone and not os.path.isdir(args.source):
        ref = sparse_clone(args.clone, args.ref, args.source, args.product_path)
        print(f"cloned {args.clone} at {ref}")

    ref = args.ref or git_sha(args.source)
    snapshot_id = args.snapshot_id or f"vault-1.21.x-{ref[:8]}"
    out_dir = args.out or os.path.join("data", "corpus", snapshot_id)

    manifest = ingest(args.source, args.product_path, snapshot_id, out_dir, ref)
    print(f"snapshot:      {manifest['snapshot_id']}")
    print(f"repo sha:      {manifest['repo_sha']}")
    print(
        "documents:     {documents} ({pages} pages + {fragment_documents} shared fragments)".format(
            **manifest
        )
    )
    print(f"parse failures: {len(manifest['parse_failures'])}")
    print(
        "chars:         structured={structured_chars}  plain={plain_chars}".format(**manifest)
    )
    print(
        "includes:      inlined={inlined} indexed_once={indexed_once} unresolved={unresolved_references}".format(
            **manifest["includes"]
        )
    )
    print(f"out:           {out_dir}")
    for failure in manifest["parse_failures"][:5]:
        print(f"  ! {failure}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
