from __future__ import annotations

import os
import tempfile

from ragqa import ingest

SAMPLE = """---
page_title: Manage secrets
description: Store and rotate secrets
---

# Manage secrets

@include 'alerts/enterprise-only.mdx'

Use the `kv` engine to store secrets.

## Options

| option | default |
| --- | --- |
| version | 2 |

<Tabs>
<Tab heading="CLI">

```bash
vault secrets enable kv
```

</Tab>
</Tabs>

<Note title="Careful">
Version 2 is not the default.
</Note>

<table><tr><th>field</th><th>type</th></tr><tr><td>path</td><td>string</td></tr></table>
"""


def test_frontmatter_is_captured_and_removed():
    meta, body = ingest.parse_mdx(SAMPLE)
    assert meta["page_title"] == "Manage secrets"
    assert meta["description"] == "Store and rotate secrets"
    assert "page_title:" not in body


def test_tab_becomes_a_heading_and_alert_becomes_a_quote():
    _, body = ingest.parse_mdx(SAMPLE)
    assert "#### CLI" in body
    assert "> Note: Careful" in body
    assert "<Tab" not in body and "<Note" not in body


def test_pipe_table_survives_and_html_table_is_converted():
    _, body = ingest.parse_mdx(SAMPLE)
    assert "| option | default |" in body
    assert "| field | type |" in body
    assert "| path | string |" in body


def test_code_fence_keeps_its_content():
    _, body = ingest.parse_mdx(SAMPLE)
    assert "```bash" in body
    assert "vault secrets enable kv" in body


def test_unresolved_include_is_dropped_and_counted():
    stats = {"inlined": 0, "marked": 0, "missing": 0}
    _, body = ingest.parse_mdx(SAMPLE, "/nonexistent/page.mdx", None, {}, stats)
    assert "enterprise-only" not in body
    assert stats["missing"] == 1


def test_shared_include_becomes_a_marker():
    workdir = tempfile.mkdtemp()
    target = os.path.join(workdir, "fragment.mdx")
    with open(target, "w", encoding="utf-8") as stream:
        stream.write("Shared alert body.")
    page = os.path.join(workdir, "page.mdx")
    text = "@include 'fragment.mdx'\n\nPage body.\n"
    with open(page, "w", encoding="utf-8") as stream:
        stream.write(text)

    roots = ingest.Roots(workdir, workdir)
    stats = {"inlined": 0, "marked": 0, "missing": 0}
    resolved = roots.resolve("fragment.mdx", page)
    assert resolved is not None
    plan = {resolved: "marker"}
    _, body = ingest.parse_mdx(text, page, roots, plan, stats)
    assert "[shared partial:" in body
    assert "Shared alert body." not in body
    assert stats["marked"] == 1


def test_plain_variant_drops_structure():
    _, body = ingest.parse_mdx(SAMPLE)
    plain = ingest.to_plain(body)
    assert "|" not in plain
    assert "#### " not in plain
    assert "```" not in plain
    assert "vault secrets enable kv" in plain


def test_doc_id_follows_the_site_convention():
    assert ingest.doc_id_for("docs/secrets/kv/index.mdx") == "docs/secrets/kv"
    assert ingest.url_for("docs/secrets/kv") == "https://developer.hashicorp.com/vault/docs/secrets/kv"
