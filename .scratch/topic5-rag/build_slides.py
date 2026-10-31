"""Build `reports/slides.pptx` — the 15-minute defence deck for the Topic 5 build.

Every figure on a slide is a file under `assets/report/`, drawn from `reports/`.
Every number on a slide also appears in `reports/report.md` with its run id; the
speaker notes carry the timing and the run id for the slide's headline number.

    python .scratch/topic5-rag/build_slides.py
"""

from __future__ import annotations

import pathlib

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIG = ROOT / "assets" / "report"
OUT = ROOT / "reports" / "slides.pptx"

W, H = Inches(13.333), Inches(7.5)
INK = RGBColor(0x1F, 0x29, 0x33)
ACCENT = RGBColor(0x1B, 0x3A, 0x5B)
MUTED = RGBColor(0x5B, 0x6B, 0x7A)
AMBER = RGBColor(0xC4, 0x7F, 0x3D)
LIGHT = RGBColor(0xF2, 0xF5, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

BODY_FONT = "Calibri"
MONO_FONT = "Consolas"


def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = Emu(0)
    frame.margin_top = frame.margin_bottom = Emu(0)
    return frame


def next_paragraph(frame):
    """Use the frame's existing empty paragraph, or append a new one."""
    if len(frame.paragraphs) == 1 and not frame.paragraphs[0].runs:
        return frame.paragraphs[0]
    return frame.add_paragraph()


def para(frame, text, size=18, bold=False, color=INK, space_before=0, space_after=6,
         first=False, align=PP_ALIGN.LEFT, mono=False, italic=False, line=1.0):
    paragraph = next_paragraph(frame)
    paragraph.alignment = align
    paragraph.space_before = Pt(space_before)
    paragraph.space_after = Pt(space_after)
    paragraph.line_spacing = line
    for chunk, is_mono in split_mono(text):
        run = paragraph.add_run()
        run.text = chunk
        run.font.size = Pt(size - 1.5 if is_mono else size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
        run.font.name = MONO_FONT if (is_mono or mono) else BODY_FONT
    return paragraph


def split_mono(text):
    """`code` spans render in the mono face."""
    parts, buffer, in_code = [], "", False
    for char in text:
        if char == "`":
            if buffer:
                parts.append((buffer, in_code))
                buffer = ""
            in_code = not in_code
            continue
        buffer += char
    if buffer:
        parts.append((buffer, in_code))
    return parts or [(text, False)]


def slide_frame(prs, title, kicker=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, Emu(0), Emu(0), W, Inches(0.09))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    head = textbox(slide, Inches(0.62), Inches(0.34), Inches(12.1), Inches(0.9))
    if kicker:
        para(head, kicker, size=11.5, bold=True, color=AMBER, first=True, space_after=2)
        para(head, title, size=27, bold=True, color=ACCENT, space_after=0)
    else:
        para(head, title, size=27, bold=True, color=ACCENT, first=True, space_after=0)
    return slide


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def hanging(paragraph, indent=Inches(0.26)):
    ppr = paragraph._p.get_or_add_pPr()
    ppr.set("marL", str(int(indent)))
    ppr.set("indent", str(int(-indent)))


def bullets(frame, items, size=16.5, gap=9):
    for index, item in enumerate(items):
        paragraph = next_paragraph(frame)
        paragraph.space_after = Pt(gap)
        paragraph.line_spacing = 1.02
        hanging(paragraph)
        marker = paragraph.add_run()
        marker.text = "▪  "
        marker.font.size = Pt(size)
        marker.font.color.rgb = AMBER
        marker.font.bold = True
        marker.font.name = BODY_FONT
        if isinstance(item, tuple):
            lead, rest = item
            for chunk, is_mono in split_mono(lead):
                run = paragraph.add_run()
                run.text = chunk
                run.font.size = Pt(size - 1.5 if is_mono else size)
                run.font.bold = True
                run.font.color.rgb = ACCENT
                run.font.name = MONO_FONT if is_mono else BODY_FONT
            for chunk, is_mono in split_mono(" " + rest):
                run = paragraph.add_run()
                run.text = chunk
                run.font.size = Pt(size - 1.5 if is_mono else size)
                run.font.color.rgb = INK
                run.font.name = MONO_FONT if is_mono else BODY_FONT
        else:
            for chunk, is_mono in split_mono(item):
                run = paragraph.add_run()
                run.text = chunk
                run.font.size = Pt(size - 1.5 if is_mono else size)
                run.font.color.rgb = INK
                run.font.name = MONO_FONT if is_mono else BODY_FONT


def stat_row(slide, y, stats, width=Inches(3.9), gap=Inches(0.18), x0=Inches(0.62), h=Inches(1.16)):
    for index, (value, label) in enumerate(stats):
        x = x0 + (width + gap) * index
        card = slide.shapes.add_shape(1, x, y, width, h)
        card.fill.solid()
        card.fill.fore_color.rgb = LIGHT
        card.line.color.rgb = RGBColor(0xDD, 0xE3, 0xE9)
        card.shadow.inherit = False
        frame = card.text_frame
        frame.word_wrap = True
        frame.margin_left = Inches(0.14)
        frame.margin_top = Inches(0.10)
        para(frame, value, size=25, bold=True, color=ACCENT, first=True, space_after=2)
        para(frame, label, size=11.5, color=MUTED, space_after=0)


def picture(slide, name, x, y, width):
    from PIL import Image
    with Image.open(FIG / name) as handle:
        w_px, h_px = handle.size
    height = width * h_px / w_px
    band_top, band_bottom = Inches(1.45), Inches(7.15)
    if y is None:
        y = band_top + int((band_bottom - band_top - height) * 0.42)
    slide.shapes.add_picture(str(FIG / name), x, y, width=width)


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1 — title
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(1, Emu(0), Emu(0), W, Inches(4.35))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    band.shadow.inherit = False
    frame = textbox(slide, Inches(0.75), Inches(1.15), Inches(11.9), Inches(2.9))
    para(frame, "A documentation knowledge base that cites what it says,",
         size=34, bold=True, color=WHITE, first=True, space_after=2, line=1.02)
    para(frame, "and says nothing when it cannot", size=34, bold=True, color=WHITE,
         space_after=14, line=1.02)
    para(frame, "CS5481 Data Engineering · Topic 5 · Group project · 24 November 2026",
         size=15, color=RGBColor(0xC9, 0xD6, 0xE2), space_after=0)
    frame = textbox(slide, Inches(0.75), Inches(4.75), Inches(11.9), Inches(1.7))
    para(frame, "Vault 1.21.x documentation · 1,268 documents · 2,318 chunks · "
               "18/18 cells finished · 60-item Golden QA Set", size=15, color=INK, first=True,
         space_after=8)
    para(frame, "Every number in this deck names a run id; the report carries the same number "
               "with its artifact.", size=13, color=MUTED, space_after=0)
    notes(slide, "0:00–0:30. Title. One sentence: we built a RAG system over pinned Vault "
                 "documentation where each claim is checked against the chunk it cites, and where "
                 "the system says it does not know. The evidence is now a complete 18-cell matrix "
                 "— eighteen finished runs, not two — plus five baseline configurations.")

    # 2 — the problem
    slide = slide_frame(prs, "The hard part is not the chatbot", "The problem")
    frame = textbox(slide, Inches(0.62), Inches(1.55), Inches(7.1), Inches(5.3), anchor=MSO_ANCHOR.MIDDLE)
    bullets(frame, [
        ("Hallucination is cheap to hide. ", "A prose answer with “[1]” in it satisfies the "
         "letter of “cite your sources” and proves nothing."),
        ("So we made the citation arithmetic. ", "Every claim carries doc_id, chunk_id and a "
         "character span; a span that does not occur in the cited chunk is rejected before any "
         "model is asked to judge it (ADR-0004)."),
        ("And the refusal is a feature. ", "A 60-item Golden QA Set holds 20 deliberately "
         "unanswerable near-misses — later releases, deployment state, a sibling product, "
         "undocumented combinations, commercial terms."),
        ("What is graded is measurement density. ", "2 chunk strategies × 3 retrieval levels × "
         "3 contextualisation levels = 18 cells, plus 10 declared sweep points and 4 baseline "
         "ablations, all on the same 60 items."),
    ], size=16.5)
    stat_row(slide, Inches(2.15), [("40", "answerable items"), ("20", "near-misses")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    stat_row(slide, Inches(3.5), [("3", "retrieval levels"), ("2", "chunk strategies")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    stat_row(slide, Inches(4.85), [("9", "error classes"), ("17", "ADRs")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    notes(slide, "0:30–1:20. Frame the problem as engineering, not prompting. Land the two "
                 "design commitments: containment before judging, and near-misses as first-class "
                 "data. Do not read the number cards aloud; they are there to be seen.")

    # 3 — how the system is built
    slide = slide_frame(prs, "Pipeline: eight stages, one snapshot id", "Architecture")
    frame = textbox(slide, Inches(0.62), Inches(1.45), Inches(11.9), Inches(5.5), anchor=MSO_ANCHOR.TOP)
    stages = [
        ("1  Corpus", "Vault 1.21.x, commit-pinned; 1,268 documents, 5.62 M characters"),
        ("2  Parse", "structure-aware + stripped text, twice, so parse value is measurable"),
        ("3  Chunk", "fixed 512/64  |  recursive parent-child, tables and code atomic (ADR-0010)"),
        ("4  Contextualise", "plain  |  generated prefix, index-side only (ADR-0013)  |  "
                             "late chunking, 2,048-token windows (ADR-0015)"),
        ("5  Index", "Qdrant, dense + sparse, keyed to one corpus snapshot"),
        ("6  Retrieve", "dense  |  hybrid + RRF  |  hybrid + cross-encoder rerank, k=10 (ADR-0011)"),
        ("7  Generate", "hosted LLM returns JSON claims with doc_id, chunk_id, span, quote"),
        ("8  Verify", "containment → NLI → hosted judge; abstain explicitly when unsupported"),
    ]
    for index, (name, detail) in enumerate(stages):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(9)
        run = paragraph.add_run()
        run.text = name.ljust(0)
        run.font.size = Pt(15)
        run.font.bold = True
        run.font.color.rgb = ACCENT
        run.font.name = BODY_FONT
        run = paragraph.add_run()
        run.text = "   " + detail
        run.font.size = Pt(14.5)
        run.font.color.rgb = INK
        run.font.name = BODY_FONT
    notes(slide, "1:20–2:15. Walk the eight stages in one breath each. The two claims worth "
                 "pausing on: parsing twice makes “is structure worth anything here” an observable "
                 "quantity, and the prefix is index-side only so the contextualisation factor "
                 "cannot leak into the prompt.")

    # 4 — citation contract
    slide = slide_frame(prs, "Three verification layers, and only one may gate", "Grounding")
    frame = textbox(slide, Inches(0.62), Inches(1.55), Inches(6.5), Inches(5.3), anchor=MSO_ANCHOR.MIDDLE)
    bullets(frame, [
        ("Containment — arithmetic. ", "The quoted span must occur inside the cited chunk and "
         "the offsets must delimit it. Catches the citation that points nowhere."),
        ("NLI cross-encoder — local, free. ", "DeBERTa-v3 MNLI/FEVER/ANLI entailment over the "
         "whole chunk."),
        ("Hosted judge — `deepseek-v4-pro`. ", "Deliberates; costs ¥1.45 per 1,000 claims, and "
         "¥0.31 graded answer correctness for all 18 cells."),
    ], size=16)
    frame = textbox(slide, Inches(7.55), Inches(1.55), Inches(5.15), Inches(5.2))
    para(frame, "Calibrated on 30 hand-labelled claims", size=15, bold=True, color=ACCENT,
         first=True, space_after=8)
    rows = [
        ("containment", "κ 0.00", "advisory"),
        ("NLI", "κ 0.59", "below the 0.60 bar"),
        ("judge", "κ 0.86", "gates reporting"),
    ]
    for name, kappa, role in rows:
        paragraph = frame.add_paragraph()
        paragraph.space_after = Pt(7)
        for text, size, colour, bold in ((f"{name:14}", 14, INK, False),
                                         (f"{kappa}   ", 14, ACCENT, True),
                                         (role, 13, MUTED, False)):
            run = paragraph.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = colour
            run.font.name = MONO_FONT if name != role else BODY_FONT
    para(frame, "Every disagreement between the layers is NLI-only (5 of 30): its errors are "
                "one-sided and inflate support, so it cannot gate the number they inflate.",
         size=13, color=MUTED, space_before=8, space_after=0, line=1.05)
    notes(slide, "2:15–3:30. This is the design claim: verify what is checkable in code before "
                 "asking a model for an opinion. Numbers from notes/judge-calibration.md, "
                 "recomputed in reports/judges.md: κ 0.857 judge, 0.595 NLI, 0.000 containment. "
                 "Cost corrected in this pass: ¥0.0436 for 30 calls is ¥1.4519 per 1,000 claims, "
                 "not ¥0.15. Say plainly that no matrix cell ran the judge, so the citation columns "
                 "in the matrix are containment, not support.")

    # 5 — design
    slide = slide_frame(prs, "18 cells, 60 items, paired tests fixed in advance", "Experiment design")
    frame = textbox(slide, Inches(0.62), Inches(1.45), Inches(7.4), Inches(5.5), anchor=MSO_ANCHOR.MIDDLE)
    bullets(frame, [
        ("3 factors × 2 × 3 × 3 = 18 cells. ", "Chunk strategy, retrieval mode, "
         "contextualisation. One configuration file per cell, one code baseline, one pinned commit "
         "(ADR-0003)."),
        ("Paired by item. ", "McNemar exact, two-sided, on discordant pairs; 10,000-resample "
         "bootstrap intervals whose resample unit is the item, not the claim."),
        ("60 items, five strata. ", "fact lookup 10, parameter values 8, table content 8, "
         "multi-hop 8, concept 6 — plus 20 near-misses."),
        ("Cut on purpose. ", "graph index, ColBERT, fine-tuning, OCR/table structure, "
         "multi-tenant auth, UI beyond one screen."),
    ], size=15.5)
    frame = textbox(slide, Inches(8.35), Inches(1.62), Inches(4.35), Inches(4.6))
    para(frame, "Why 60 and not 20", size=15, bold=True, color=ACCENT, first=True, space_after=8)
    para(frame, "24 answerable items → ~5 discordant pairs → McNemar p≈0.38: undetectable.",
         size=13.5, color=INK, space_after=8, line=1.05)
    para(frame, "60 answerable items → ~12 discordant pairs → 10:2, p≈0.04: detectable.",
         size=13.5, color=ACCENT, space_after=8, line=1.05)
    para(frame, "Set size, not cell count, decides whether any claim here can carry a significance "
                "marker.", size=13, color=MUTED, space_after=0, line=1.05)
    notes(slide, "3:30–4:40. Design slide; keep it brisk. The one thing to defend out loud is the "
                 "set size: the paired test's power depends on discordant pairs, which is why 60 "
                 "and not the brief's 20. Then the omissions — each has an ADR with a reason, and "
                 "we name the reason rather than the omission.")

    # 6 — status, honestly
    slide = slide_frame(prs, "Status: 18 of 18 cells, and two null results", "Where we are")
    frame = textbox(slide, Inches(0.62), Inches(1.55), Inches(11.2), Inches(5.2))
    bullets(frame, [
        ("Finished. ", "Eighteen cells, one run each, joined by recomputed config digest: zero "
         "drift, zero orphans, zero unreadable runs (`reports/matrix.md`)."),
        ("Two factors move nothing. ", "Chunk strategy averages 0.7944 against 0.8167 hit@10 and "
         "no one of nine paired comparisons clears p = 0.05; the contextual prefix is null against "
         "plain (citation p = 0.82, abstention p = 0.58)."),
        ("Three contrasts clear the bar. ", "Late chunking loses to plain on retrieval (54 of 240 "
         "paired items, p < 0.000001), citation (p = 0.000007) and abstention (p < 0.000001); "
         "reranked retrieval loses to hybrid on citation (p = 0.0357)."),
        ("Finished too. ", "ten sweep points across three curves, and five baseline configurations (§3.3, §3.7)."),
    ], size=16)
    para(frame, "A null result with a mechanism behind it is a finding; an absent cell is not.",
         size=15, italic=True, color=AMBER, space_before=10, space_after=0)
    notes(slide, "4:40–5:30. Say this before the results, not after. The aggregation refuses to "
                 "fill a missing cell, so the report and the deck cannot drift from the runs — and "
                 "now that every cell exists, the interesting output is that two factors are null "
                 "and the citation layer is where the differences are.")

    # 7 — matrix results
    slide = slide_frame(prs, "Late chunking is the only factor that moves retrieval",
                        "Results · matrix")
    frame = textbox(slide, Inches(0.62), Inches(1.42), Inches(6.1), Inches(2.9))
    para(frame, "hit@10, mean over the cells of each level", size=13.5, bold=True, color=ACCENT,
         first=True, space_after=8)
    for label, values in (
        ("retrieval", "dense 0.6583  ·  hybrid 0.8792  ·  rerank 0.8792"),
        ("contextualisation", "plain 0.8833  ·  prefix 0.8750  ·  late chunking 0.6583"),
        ("chunk strategy", "fixed 0.7944  ·  recursive parent-child 0.8167"),
    ):
        para(frame, label, size=12.5, color=MUTED, space_after=1, line=1.0)
        para(frame, values, size=13.5, color=INK, space_after=9, line=1.05)
    para(frame, "Each mean over 6 cells (chunk strategy: 9). Source `reports/matrix.md`; all 18 "
                "runs are in the report's Table 1 and Appendix A.1.",
         size=11.5, color=MUTED, space_after=0, line=1.05)
    frame = textbox(slide, Inches(7.0), Inches(1.42), Inches(5.7), Inches(5.4))
    para(frame, "What separates, and by how much", size=13.5, bold=True, color=ACCENT,
         first=True, space_after=8)
    for value, label in (
        ("b = 0 / c = 54", "late chunking vs plain, retrieval hit@10 of 240 paired items, "
                           "p < 0.000001"),
        ("p = 0.000007", "late chunking vs plain, grounded citation — 5 to 32"),
        ("p < 0.000001", "late chunking vs plain, abstention decision — 1 to 32"),
        ("p = 0.0357", "rerank vs hybrid, grounded citation — 8 items to 20, hybrid wins"),
        ("p ≥ 0.5000", "every chunking pair on hit@10; every prefix pair on everything"),
    ):
        paragraph = frame.add_paragraph()
        paragraph.space_after = Pt(5)
        run = paragraph.add_run()
        run.text = value + "   "
        run.font.size = Pt(14)
        run.font.bold = True
        run.font.color.rgb = AMBER
        run.font.name = BODY_FONT
        run = paragraph.add_run()
        run.text = label
        run.font.size = Pt(12)
        run.font.color.rgb = INK
        run.font.name = BODY_FONT
    para(frame, "hit@10 carries a 10,000-resample item bootstrap (0.8500 [0.7250, 0.9500] for the "
                "reference cell; MRR and nDCG@10 have none, because a rank cannot be recovered from "
                "a committed run directory).", size=11.5, color=MUTED,
         space_before=6, space_after=0, line=1.05)
    stat_row(slide, Inches(4.75), [
        ("0.025", "mean-pooled query hit@10, against 0.275 with CLS"),
        ("0 / 10", "items the pooling swap recovered / lost"),
        ("0.8792", "hybrid and rerank, tied on hit@10"),
    ], width=Inches(1.95), gap=Inches(0.12), h=Inches(1.6))
    notes(slide, "5:30–6:50. Numbers: reports/matrix.md main effects, reports/significance.md "
                 "contrasts, notes/late-pooling-probe.md. The retrieval interval is real again "
                 "(0.8500 [0.7250, 0.9500], seed 11706917); mrr and ndcg deliberately print "
                 "missing. The single finding to land: late chunking costs the dense branch 54 of "
                 "240 paired retrieval items, and mean-pooling the query as well makes it worse "
                 "(0.275 → 0.025 hit@10, 10 items lost, none gained), so the failure is the "
                 "encoder's geometry, not the technique.")

    # 8 — abstention
    slide = slide_frame(prs, "Abstention: a rank-fusion score is not a confidence", "Results · abstention")
    picture(slide, "fig1-abstention.png", Inches(0.5), Inches(1.5), Inches(8.1))
    frame = textbox(slide, Inches(8.75), Inches(1.55), Inches(4.0), Inches(3.4))
    bullets(frame, [
        ("18-point sweep, 60 items.", "Rule fixed first: max F1 subject to over-abstention ≤ 0.05."),
        ("Only dense fits.", "t = 0.5706 → 38/40 answered, 17/20 near-misses answered, over 0.050."),
        ("Hybrid and rerank cannot.", "Infeasible at all 18 points; fallback gives 0.075 and 0.150."),
        ("Hybrid is a plateau.", "Three grid points return the identical operating point "
         "(0.6607 / 0.9250): an RRF sum takes a few lattice values."),
    ], size=12.5, gap=6)
    para(frame, "In the matrix the thresholds are 0.2 / 0.01 / 0.0 and every refusal is the "
                "generator's own: 20 of 20 near-misses refused in all 18 cells.",
         size=12, color=AMBER, space_before=6, space_after=0, line=1.05)
    stat_row(slide, Inches(4.85), [
        ("0.5706", "dense · 38/40 answered, 17/20 near-misses"),
        ("0.028606", "hybrid · budget infeasible, 37/40 answered"),
        ("0.426134", "rerank · on the grid floor, 34/40 answered"),
    ], width=Inches(2.62), gap=Inches(0.12), h=Inches(1.25))
    notes(slide, "6:50–8:00. Source reports/abstention/working-points.json and {dense,hybrid,rerank}"
                 "-pr.csv. Working points: dense t 0.5706 (raw 0.570600, P 0.691, R 0.950); hybrid "
                 "t 0.2824 (raw 0.028606, P 0.661, R 0.925); rerank t 0.2000 (raw 0.426134, P "
                 "0.739, R 0.850). The honest caveat is the amber line: the matrix's abstention "
                 "columns measure the generator, not the tuned operating point.")

    # 9 — error taxonomy
    slide = slide_frame(prs, "275 failures, and 71 % of them are evidence that never arrived",
                        "Diagnosis")
    stat_row(slide, Inches(1.5), [
        ("157", "document misses, on 25 items"),
        ("39", "chunk misses, from 12 items"),
        ("29", "window drops — k = 10, window = 8"),
    ], width=Inches(3.85), gap=Inches(0.2), h=Inches(1.3))
    frame = textbox(slide, Inches(0.62), Inches(3.05), Inches(6.0), Inches(3.2))
    bullets(frame, [
        ("196 of 275 are lost evidence.", "71 % never reached the prompt: retrieval, boundaries and "
         "the context window, not the reader."),
        ("Zero over-abstention is derived.", "All 64 refusals on answerable items are exactly the "
         "64 items whose evidence was lost first — 43 doc misses, 13 chunk misses, 8 window drops."),
        ("Quotes and parses are the small end.", "26 mangled quotes (8 are flattened markdown "
         "links) and 17 unparsable replies, on 1,080 item-cells."),
    ], size=13, gap=7)
    frame = textbox(slide, Inches(6.95), Inches(3.05), Inches(5.8), Inches(3.2))
    para(frame, "What it cannot see", size=14, bold=True, color=ACCENT, first=True, space_after=8)
    para(frame, "Every cell ran with `judge_enabled = false`, so an answer that is wrong while its "
                "citations check out is invisible: these are lost-evidence and malformed-output "
                "events — an upper bound on answer errors, not a wrong-answer count.",
         size=13, color=INK, space_after=8, line=1.05)
    para(frame, "hit@10 is any-of: it returns on the first gold quote it finds, so 56 of the 196 "
                "evidence-loss events sit on items the matrix scored as hits. Recall over every "
                "gold quote is 0.73, not 0.81.", size=12.5, color=MUTED, space_after=0, line=1.05)
    frame = textbox(slide, Inches(0.62), Inches(6.35), Inches(12.1), Inches(0.8))
    para(frame, "A028 misses its page in all 18 cells; A034 and A035 theirs in all 18; A030 in 17. "
                "The pages are absent, not mis-ranked.", size=13.5, italic=True, color=ACCENT,
         first=True, space_after=0, line=1.08)
    notes(slide, "8:00–9:00. Short: the taxonomy routes every later experiment. 275 events across "
                 "all eighteen cells, 40 hand-inspected (notes/error-taxonomy.{md,json}). The three "
                 "numbers to say aloud: 196/275 lost before generation; 64 abstentions = 64 "
                 "evidence losses; 29 chunks dropped between k = 10 and the eight-chunk window. "
                 "Then the caveat: judge off, so this bounds answer errors without counting them, "
                 "and hit@10 is any-of, which is why recall over all gold quotes is 0.73.")

    # 10 — DEMO
    slide = slide_frame(prs, "Demo: a citation you can click, an abstention you can inspect",
                        "Minute nine · live demo")
    frame = textbox(slide, Inches(0.62), Inches(1.45), Inches(6.3), Inches(5.5), anchor=MSO_ANCHOR.MIDDLE)
    bullets(frame, [
        ("A001 — three claims, three spans.", "Click [2]: the highlight is the second claim, not "
         "the first."),
        ("A007 — a table row, not prose.", "The parent-child chunk kept the table whole."),
        ("A009 — the pipeline withholding itself.", "One claim fails `quote_not_in_chunk`; no "
         "marker, failure class shown."),
        ("U008 — the near-miss that abstains.", "Best chunk scores 0.669 — above the threshold — "
         "and the answer is still withheld."),
    ], size=15)
    frame = textbox(slide, Inches(7.3), Inches(1.6), Inches(5.45), Inches(4.9))
    para(frame, "If the gateway or the GPU is not there", size=14, bold=True, color=ACCENT,
         first=True, space_after=8)
    para(frame, "1. Replay from the response cache — same configuration, same answers, no network "
                "(`generation 1 ms`).", size=13, color=INK, space_after=7, line=1.05)
    para(frame, "2. Fixture configuration — eleven chunks, hashed embedder, stub generator: same "
                "screen, same markers, same abstention path.", size=13, color=INK,
         space_after=7, line=1.05)
    para(frame, "Startup: 38.9 s, 2,203 chunks, loaded once. Chainlit on :8000.",
         size=12.5, color=MUTED, space_after=0, line=1.05)
    notes(slide, "9:00–11:15. DEMO. Type the question, do not just talk over the screen. Order: "
                 "A001, A007, A009, U008. If the model is slow, fall back to the cache replay and "
                 "say you are doing it. Keep the U008 explanation for last: 0.669 is above the "
                 "threshold, so the refusal is the generator's, which is the honest story. "
                 "Script and captured outputs: notes/demo-script.md.")

    # 11 — the three sensitivity curves
    slide = slide_frame(prs, "Depth buys recall and dilutes the ranking", "Results · sensitivity")
    picture(slide, "fig2-sweeps.png", Inches(0.45), Inches(1.5), Inches(8.5))
    frame = textbox(slide, Inches(9.15), Inches(1.55), Inches(3.6), Inches(3.3))
    bullets(frame, [
        ("Depth saturates at k = 20.", "recall 0.8750 → 0.9000 → 1.0000 → 1.0000, while MRR peaks "
         "at k = 5 (0.6458) and citation precision at k = 10."),
        ("512 words is dominated.", "256 retrieves more (0.9500 against 0.9000) for ¥3.50 less per "
         "1,000 questions."),
        ("The loop pays once.", "2.5 recall points for ¥0.62 at hop 2; the third hop buys nothing — "
         "break-even is hop 2."),
    ], size=12, gap=6)
    para(frame, "Deep lists recover the tail and dilute the head: the generator sees eight chunks "
                "however deep the retrieval went.", size=11.5, italic=True, color=AMBER,
         space_before=6, space_after=0, line=1.05)
    stat_row(slide, Inches(4.85), [
        ("1.0000", "recall at k = 20, and no gain at k = 40"),
        ("0.6458", "MRR at k = 5 — the shallowest depth wins ranking"),
        ("hop 2", "break-even; the third round buys nothing"),
    ], width=Inches(4.0), gap=Inches(0.15), h=Inches(1.25))
    notes(slide, "11:15–11:55. Ten finished points, reports/sweeps/{k,chunk,hops}.{csv,md}. Say the "
                 "two things a reader does not expect: more depth does not raise MRR (0.6458 at "
                 "k = 5 against 0.5985 at k = 10), and the matrix's own 512-word chunk is beaten on "
                 "both recall and price by 256. Hop break-even is hop 2 with a marginal ¥24.7 per "
                 "recall point, and all three hop points share one trigger, 0.426134.")

    # 12 — answer correctness
    slide = slide_frame(prs, "Correctness: right answer, not just the right passage",
                        "Results · answer correctness")
    stat_row(slide, Inches(1.55), [
        ("0.9000", "best cell, all 40 answerable items"),
        ("0.8139", "mean over the 18 cells"),
        ("0.4250", "floor — fixed / dense / late chunking"),
    ], width=Inches(3.85), gap=Inches(0.2), h=Inches(1.35))
    frame = textbox(slide, Inches(0.62), Inches(3.15), Inches(6.1), Inches(3.6))
    para(frame, "How it is measured", size=14, bold=True, color=ACCENT, first=True, space_after=8)
    para(frame, "One `deepseek-v4-pro` call per answered item: does the generated answer agree with "
                "the item's reference answer? An abstention is never correct, so the two rates "
                "differ only in the denominator.", size=13, color=INK, space_after=8, line=1.05)
    para(frame, "This is correctness against a reference, not faithfulness — the cited chunks can "
                "support a wrong answer, and GLOSSARY keeps the two apart on purpose.",
         size=13, color=MUTED, space_after=0, line=1.05)
    frame = textbox(slide, Inches(7.0), Inches(3.15), Inches(5.7), Inches(3.6))
    para(frame, "The numbers", size=14, bold=True, color=ACCENT, first=True, space_after=8)
    para(frame, "0.4250–0.9000 over all 40 answerable items · 0.7083–0.9474 over the items each "
                "cell answered.", size=13, color=INK, space_after=8, line=1.05)
    para(frame, "Excluding the six late-chunking cells: 0.7500–0.9000 and 0.8205–0.9231.",
         size=13, color=INK, space_after=8, line=1.05)
    para(frame, "¥0.3104 for 656 judge calls — the whole matrix, graded once.",
         size=13, color=AMBER, space_after=0, line=1.05)
    band = slide.shapes.add_shape(1, Inches(0.62), Inches(5.35), Inches(12.1), Inches(1.1))
    band.fill.solid()
    band.fill.fore_color.rgb = LIGHT
    band.line.color.rgb = RGBColor(0xDD, 0xE3, 0xE9)
    band.shadow.inherit = False
    frame = textbox(slide, Inches(0.82), Inches(5.52), Inches(11.7), Inches(0.9))
    para(frame, "Five cells reach 0.9000 — fixed/rerank/plain, fixed/rerank/late, "
                "recursive/hybrid/plain, recursive/hybrid/late, recursive/rerank/plain. The floor is "
                "the two dense late-chunking cells at 0.4250 and 0.4750, where 16 and 14 of 40 "
                "answerable items were refused: correctness and hit@10 fall together.",
         size=12.5, color=INK, first=True, space_after=0, line=1.08)
    notes(slide, "11:55–12:35. This slide closes brief item 5, which asked for hit rate AND answer "
                 "correctness. Source reports/correctness.json and notes/correctness.md: 18 cells, "
                 "656 judge calls, 227,829/20,608 tokens, ¥0.3104, 243 cache hits, no parse "
                 "failure. The interpretation worth saying out loud: the two dense late-chunking "
                 "cells fall to 0.4250 and 0.4750 because they abstained on 16 and 14 of 40 — "
                 "correctness and hit@10 fall together.")

    # 13 — cost
    slide = slide_frame(prs, "Long context is cheaper, and that costs us the citation",
                        "Cost · baselines")
    stat_row(slide, Inches(1.5), [
        ("¥4.24", "long context per 1,000 questions"),
        ("¥9.10", "the reference cell, same 60 items"),
        ("2.0×", "the real gap — not 3×"),
    ], width=Inches(3.85), gap=Inches(0.2), h=Inches(1.3))
    frame = textbox(slide, Inches(0.62), Inches(3.05), Inches(6.0), Inches(3.7))
    para(frame, "Five configurations, one factor each", size=14, bold=True, color=ACCENT,
         first=True, space_after=8)
    para(frame, "Long context is 0.47× the reference cell per 1,000 questions; the prompt-shape "
                "projection agrees (¥4.77 against ¥9.54). What it loses is the citation: a claim "
                "cites a document, not a chunk, so it lands as `chunk_not_retrieved` — 36 items "
                "to 0, p = 3e-11.", size=12.5, color=INK, space_after=7, line=1.05)
    para(frame, "Closed book declines by construction (36 to 0): it bounds the context block, not "
                "the model's knowledge.", size=12.5, color=INK, space_after=0, line=1.05)
    frame = textbox(slide, Inches(6.95), Inches(3.05), Inches(5.8), Inches(3.7))
    para(frame, "The other three rows", size=14, bold=True, color=ACCENT, first=True, space_after=8)
    para(frame, "The embedder is the floor: all-MiniLM-L6-v2 takes hit@10 from 0.90 to 0.65, 13 "
                "items lost to 3 (p = 0.021).", size=12.5, color=INK, space_after=7, line=1.05)
    para(frame, "The cheap generator keeps retrieval, loses 4 citation items to 3 at half the "
                "money — a business claim, not a headline.", size=12.5, color=INK, space_after=7,
         line=1.05)
    para(frame, "Judge: ¥1.4519 per 1,000 claims. Answer correctness for all 18 cells: ¥0.3104.",
         size=12.5, color=AMBER, space_after=0, line=1.05)
    notes(slide, "12:35–13:20. Kills an argument we could have made and would have been wrong "
                 "about: the gap is 2.0×, not 3× (9.5366 / 4.7682 projected; 9.0993 / 4.2440 "
                 "measured — reports/baselines/table.md). Generator probe: 19 requests across 13 "
                 "models, $0.0017; gpt-6-luna ¥6.80 vs ¥9.54, a 29% saving. Judge cost if asked: "
                 "¥1.45 per 1,000 claims.")

    # 14 — threats
    slide = slide_frame(prs, "What is not established", "Limits")
    frame = textbox(slide, Inches(0.62), Inches(1.55), Inches(11.3), Inches(5.2))
    bullets(frame, [
        ("Citation numbers are containment.", "No matrix cell ran the judge, so precision means "
         "“the span occurs”, not “the citation supports the claim”."),
        ("Rank metrics have no interval.", "hit@10 is bootstrapped over items; MRR and nDCG@10 "
         "print `missing` — a committed run directory records which items were missed, not where "
         "the evidence ranked."),
        ("Latency is cache-dominated.", "61 of 64 LLM calls in the dense cell were cache hits: "
         "17.3 ms is a SQLite read, not a round trip."),
        ("hit@10 is any-of, not recall.", "It returns on the first gold quote it finds: 56 of the "
         "196 evidence-loss events sit on items scored as hits, and recall over every gold "
         "quote is 0.73."),
        ("No human read the golden set.", "Fourteen items were read by the agent at the "
         "group's authorisation: one defect (A038), three quotes containable but not "
         "self-locating. Containment proves a quote is real, not that it is sufficient."),
    ], size=14.5, gap=6)
    notes(slide, "13:20–14:05. Read these as commitments, not apologies: each is one line in the "
                 "report's threats-to-validity section, and each names what would fix it. The "
                 "intervals were repaired in this pass — hit@10 is real, and only the rank metrics "
                 "stay absent, on purpose (reports/significance.csv).")

    # 15 — what next
    slide = slide_frame(prs, "With more time, in the order the taxonomy justifies", "Next")
    frame = textbox(slide, Inches(0.62), Inches(1.55), Inches(11.4), Inches(5.0))
    steps = [
        ("1  Late chunking on a mean-pooling encoder.",
         "`jina-embeddings-v2`, or an e5/gte model: the only test of the mechanism rather than of "
         "bge-m3's CLS geometry."),
        ("2  Run the ten sweep points.",
         "The chunk-size curve tests chunk resolution, the one mechanism the nine pairs could not."),
        ("3  Judge-enabled headline cells.",
         "So citation precision stops meaning containment."),
        ("4  Parent-chunk generation.",
         "`parent_id` already travels through retrieval; citing the child while reading the parent "
         "needs one span field, not a re-index (ADR-0017)."),
        ("5  Scale the hand taxonomy to 18 cells.", "So the class counts stop resting on 120 items."),
        ("6  A human reads the 60 items.", "The one threat no compute removes."),
    ]
    for lead, rest in steps:
        paragraph = frame.paragraphs[0] if lead.startswith("1") else frame.add_paragraph()
        paragraph.space_after = Pt(11)
        paragraph.line_spacing = 1.04
        for chunk, is_mono in split_mono(lead):
            run = paragraph.add_run()
            run.text = chunk
            run.font.size = Pt(15.5 - 1.5 if is_mono else 15.5)
            run.font.bold = True
            run.font.color.rgb = ACCENT
            run.font.name = MONO_FONT if is_mono else BODY_FONT
        for chunk, is_mono in split_mono("  " + rest):
            run = paragraph.add_run()
            run.text = chunk
            run.font.size = Pt(14.5 - 1.5 if is_mono else 14.5)
            run.font.color.rgb = INK
            run.font.name = MONO_FONT if is_mono else BODY_FONT
    notes(slide, "14:05–14:35. One line per item, no elaboration beyond the first. The order is the "
                 "taxonomy's, not ours: the class that the next factor can move comes first, and "
                 "the sweep points are cheaper than any new cell because the configurations are "
                 "already emitted and gated.")

    # 16 — close
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(1, Emu(0), Inches(2.0), W, Inches(3.1))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    band.shadow.inherit = False
    frame = textbox(slide, Inches(0.75), Inches(2.35), Inches(11.9), Inches(2.4))
    para(frame, "Grounded or silent — and both are measured.", size=30, bold=True, color=WHITE,
         first=True, space_after=12, line=1.05)
    para(frame, "0.8792 mean hit@10 (hybrid, rerank) · 1.0000 abstention recall, all 18 cells · "
                "0.9000 best correctness · ¥8.46 per 1,000 questions",
         size=15, color=RGBColor(0xC9, 0xD6, 0xE2), space_after=0)
    frame = textbox(slide, Inches(0.75), Inches(5.4), Inches(11.9), Inches(1.6))
    para(frame, "Questions — and the contribution page is the last page of the report.",
         size=14, color=INK, first=True, space_after=6)
    para(frame, "Code: `ragqa/` · artifacts: `reports/` · decisions: `docs/adr/0001`–`0017` · "
                "brief requirements 1–5 mapped in §1", size=12.5, color=MUTED, space_after=0)
    notes(slide, "14:35–15:00. Close on the two-word contract: grounded or silent. Leave the four "
                 "numbers up while questions run. If asked for the weakest number, it is the "
                 "degenerate retrieval interval in reports/significance.csv, not the accuracy.")

    prs.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    prs = Presentation(path)
    print(f"wrote {path} — {len(prs.slides._sldIdLst)} slides, {path.stat().st_size} bytes")
    for index, slide in enumerate(prs.slides, start=1):
        first = ""
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                first = shape.text_frame.text.strip().splitlines()[0][:60]
                break
        has_notes = slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
        print(f"  {index:2d}  {first:60s}  notes={'yes' if has_notes else 'NO'}")
