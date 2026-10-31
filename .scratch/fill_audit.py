"""Fill the verdicts into notes/golden-audit.md after reading the items."""

from __future__ import annotations

import pathlib

VERDICTS = {
    "A001": ("pass (weak)", "Criterion 3 only: *Vault starts sealed* is the first fact in almost every Vault tutorial, so a reader with product experience answers it without the document. Kept because an anchor item that a stumbler cannot miss is useful for detecting a broken pipeline; do not count it as evidence of retrieval quality."),
    "A008": ("pass", "Question names the metric; quote defines it; the reference answer restates the quote and adds nothing (0.818 answer-token overlap, similarity 0.67)."),
    "A015": ("pass (caveat)", "The quote is `The value is the number of entries and the default value is **131072**.` — it never names the cache. It is the storage read cache: the preceding sentence reads *Vault uses a Least Recently Used (LRU) read cache for the physical storage subsystem with a tunable value, `cache_size`*, under `### Cache size`. So the **doc_id plus section** carry the anchor while the quote alone does not; a claim quoting this sentence is containable but not self-locating. v2 should extend the quote to the LRU sentence."),
    "A022": ("pass (caveat)", "The quote is one table row, `| Rate limit quotas | Limit maximum amount of requests per second (RPS) … | ✅ | ✅ |`. The two check marks are meaningless without the header row naming the editions, and the reference answer (`both editions support them`) does not stand on the quoted row. The table is the *point* of this stratum — a naive chunker loses the header, and this item detects exactly that — so the item is worth keeping, but the recorded evidence under-supports its own answer. v2 should include the header row."),
    "A030": ("pass", "Two documents, two quotes, and the inference between them is the stratum's purpose: remount revokes leases, every dynamic secret carries a lease, therefore issued credentials go. The reference answer states the inference explicitly, which is what a graded answer should contain."),
    "A035": ("pass", "Quote is the mechanism, answer is its purpose, no fact beyond the quote (0.5 overlap)."),
    "A005": ("pass (weak)", "Quote says tokens carry a prefix that indicates their type; the question asks specifically batch versus service, and neither the quote nor the reference answer names the two prefixes. Answerable from the page, but the item's specificity is lower than its stratum suggests."),
    "A006": ("pass", "`Only a single recovery token can be generated.` against `Exactly one.` — the reference answer shares **zero** tokens with its quote, and that is a tokenisation artefact, not a defect. This is the counter-example that shows why the overlap signal is a screen and not a verdict."),
    "A028": ("pass (caveat)", "First quote is self-contained (recovery keys replace unseal keys at initialisation). The second, `These are still required for highly privileged actions, such as generating new root keys.`, starts with a pronoun whose antecedent sits in the previous sentence of that document. A claim citing it is containable but its support depends on text the verifier never sees. v2 should extend that quote by one sentence."),
    "A038": ("**defect (mild)**", "The reference answer says more than its evidence: *stores different encryption keys for different purposes, **and rotation then targets the key that needs changing***. The quoted sentence supports only the first clause (answer-token overlap 0.353). The answer is true of the page, so the item is not unanswerable — but a correct answer that mentions rotation cannot be supported by the quote as recorded. v2 must either extend the quote or drop the second clause."),
    "U003": ("pass", "Checked by search rather than by reading: `disable_gzip` occurs in **0 of 1,268** documents, so asking for its 1.22 default is genuinely unanswerable, and the nearest document exists and shares vocabulary with the question."),
    "U008": ("pass", "Asks for the current raft log size on *my* nodes — runtime state of a specific cluster. The nearest page describes snapshot thresholds, so the topically-adjacent-but-unanswerable condition holds."),
    "U014": ("pass", "Asks how to move **off** Integrated Storage; the corpus documents only the reverse migration (Consul → Integrated Storage). Direction-specific absence is the cleanest kind of near-miss here."),
    "U019": ("pass", "Asks for a commercial tier's seat allowance; the corpus discusses client counting and names no HCP tier. Commercial packaging, adjacent page present."),
}

SCREEN = """\
## Screen over all forty answerable items

The three caveats above share one measurable property: the question's content words barely
appear in its own evidence. Screening all forty answerable items by that overlap (question
tokens present in the quote) flags six below 0.25, and all four that were then read are
above; the other two are `A015` and `A022`, already read:

| id | stratum | question overlap | answer overlap | read | verdict |
|---|---|---|---|---|---|
| A005 | fact_lookup | 0.062 | 0.375 | yes | pass (weak) |
| A006 | fact_lookup | 0.214 | **0.000** | yes | pass — artefact |
| A015 | param_value | 0.167 | 1.000 | yes | pass (caveat) |
| A022 | table_content | 0.214 | 0.375 | yes | pass (caveat) |
| A028 | multi_hop | 0.176 | 0.875 | yes | pass (caveat) |
| A038 | concept | 0.231 | 0.353 | yes | **defect (mild)** |

So the screen found a real defect (A038) and three quote-extension candidates, and it also
produced one false alarm (A006, zero overlap for a semantically exact answer). Use it to
choose what to read; never use it to decide.

"""

FINDINGS = """\
## Findings and what they imply

Fourteen items were read (ten stratified, plus the four the screen flagged hardest). **One
defect and three under-specified quotes, thirteen passes.**

1. **One real defect, `A038`**: the reference answer asserts a rotation consequence that its
   quoted sentence does not contain. The answer is true of the page, so no number in the
   report is wrong; what is wrong is that a correct answer mentioning rotation cannot be
   supported by the recorded evidence.
2. **Three quotes are containable but not self-locating** (`A015`, `A022`, `A028`): a pronoun
   whose antecedent is outside the quote, a table row without its header, a sentence about
   "the value" that never names the setting. This is a property of sentence-level quotes in
   reference documentation, not sloppiness, and it is worth stating in the report because it
   is exactly what the containment check cannot see: **containment proves the quote is real,
   not that the quote is sufficient**.
3. **One item is answerable from general knowledge** (`A001`). Kept deliberately as an anchor.
4. **The overlap signal is a screen, not a verdict** (`A006`).

### Proposed `golden/v2.jsonl` edits (v1 is immutable)

| id | change | cost if not made |
|---|---|---|
| A038 | extend the evidence quote to the rotation sentence, or drop *and rotation then targets the key that needs changing* from the reference answer | the item systematically counts a correct answer as unsupported |
| A015 | extend the quote one sentence, to include *Vault uses a Least Recently Used (LRU) read cache for the physical storage subsystem with a tunable value, `cache_size`* | the quote alone does not say which setting it describes |
| A022 | include the table's header row in the quote | the recorded evidence cannot support "both editions" |
| A028 | extend the second quote by one sentence so its pronoun has an antecedent | same, for the recovery-key half |

None of the four changes the corpus, the strata quotas, or any metric that has already been
reported: they change what the *evidence field* contains, which is what a re-chunk and a
re-verification read. Adopting them means regenerating `golden/v2.jsonl`, re-running the
eighteen cells and the four baselines, and re-deriving every table — which is why they are
recorded here rather than applied at the end of the build.

### What this audit is, and is not

It is the implementing agent reading fourteen items against the corpus, at the group's
authorisation, with every quote printed verbatim and every signal reproducible by
`python scripts/golden_audit.py --ids …`. It is **not** an independent human review, and
the report says so: `verified_by` stays `automated:corpus-anchored` on all sixty items. What
changed is that the project now knows the size of the gap: **one defect in fourteen read**,
and a screen that can point a human at the remaining twenty-six answerable items in a
minute.

"""


def main() -> int:
    path = pathlib.Path("notes/golden-audit.md")
    text = path.read_text(encoding="utf-8")

    text = text.replace(
        f"Ten items of `golden/v1.jsonl` ({len(VERDICTS)} rows), read one by one against the corpus.",
        f"Fourteen items of `golden/v1.jsonl`, read one by one against the corpus: ten stratified "
        f"across the strata (six answerable, four near-miss), plus the four that a question/quote "
        f"overlap screen over all forty answerable items flagged hardest.",
    )
    text = text.replace("## The ten", "## The fourteen")

    for item_id, (verdict, note) in VERDICTS.items():
        old = f"| {item_id} |"
        # fill the verdict column of the summary table row for this id
        for line in text.splitlines():
            if line.startswith("|") and f"| {item_id} |" in line and line.rstrip().endswith("| |"):
                cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
                cells[-2] = verdict
                cells[-1] = note.replace("|", "\\|")
                new_line = "| " + " | ".join(cells) + " |"
                text = text.replace(line, new_line)
                break

    text = text.replace(
        "_(filled after reading; a defect means `golden/v2.jsonl`, never an edit to v1)_",
        FINDINGS.strip(),
    )
    if "## Screen over all forty" not in text:
        text = text.replace("## Findings and what they imply", SCREEN + "## Findings and what they imply", 1)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("verdicts written into notes/golden-audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
