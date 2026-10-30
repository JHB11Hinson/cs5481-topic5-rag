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


def stat_row(slide, y, stats, width=Inches(3.9), gap=Inches(0.18), x0=Inches(0.62)):
    for index, (value, label) in enumerate(stats):
        x = x0 + (width + gap) * index
        card = slide.shapes.add_shape(1, x, y, width, Inches(1.16))
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
        y = band_top + int((band_bottom - band_top - height) * 0.18)
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
               "18-cell matrix · 60-item Golden QA Set", size=15, color=INK, first=True, space_after=8)
    para(frame, "Every number in this deck names a run id; the report carries the same number "
               "with its artifact.", size=13, color=MUTED, space_after=0)
    notes(slide, "0:00–0:30. Title. One sentence: we built a RAG system over pinned Vault "
                 "documentation where each claim is checked against the chunk it cites, and where "
                 "the system says it does not know. Mention the measured evidence is 2 of 18 cells "
                 "and we will be explicit about that at minute 5.")

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
        ("What is graded is measurement density. ", "12 cells after the matrix, plus 3 "
         "sweeps and 5 baseline cells: chunking, retrieval, contextualisation."),
    ], size=16.5)
    stat_row(slide, Inches(2.15), [("40", "answerable items"), ("20", "near-misses")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    stat_row(slide, Inches(3.5), [("3", "retrieval levels"), ("2", "chunk strategies")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    stat_row(slide, Inches(4.85), [("9", "error classes"), ("17", "ADRs")],
             width=Inches(2.35), gap=Inches(0.16), x0=Inches(8.05))
    notes(slide, "0:30–1:30. Frame the problem as engineering, not prompting. Land the two "
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
    notes(slide, "1:30–2:30. Walk the eight stages in one breath each. The two claims worth "
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
        ("Hosted judge — `deepseek-v4-pro`. ", "Deliberates; costs about ¥0.15 per 1,000 claims."),
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
    notes(slide, "2:30–3:45. This is the design claim: verify what is checkable in code before "
                 "asking a model for an opinion. Numbers from notes/judge-calibration.md, "
                 "recomputed in reports/judges.md: κ 0.857 judge, 0.595 NLI, 0.000 containment. "
                 "Say plainly that no matrix cell ran the judge, so the citation columns in the "
                 "matrix are containment, not support.")

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
    para(frame, "Set size, not cell count, decides whether any claim can carry a significance "
                "marker.", size=13, color=MUTED, space_after=0, line=1.05)
    notes(slide, "3:45–5:00. Design slide; keep it brisk. The one thing to defend out loud is the "
                 "set size: the paired test's power depends on discordant pairs, which is why 60 "
                 "and not the brief's 20. Then the omissions — each has an ADR with a reason, and "
                 "we name the reason rather than the omission.")

    # 6 — status, honestly
    slide = slide_frame(prs, "Status first: 2 of 18 cells have finished runs", "Where we are")
    frame = textbox(slide, Inches(0.62), Inches(1.6), Inches(11.0), Inches(5.0))
    bullets(frame, [
        ("Finished. ", "`cell-fixed-dense-plain` and `cell-fixed-hybrid-plain` — 60 items each, "
         "runs `…8ae4eb06` and `…6170ae66`."),
        ("Missing. ", "16 cells print `missing` in `reports/matrix.md`; the aggregate refuses to "
         "interpolate, and so does the report."),
        ("Unestimated, not zero. ", "Interaction terms print 0 by construction with 2 of 4 corners "
         "present, and all nine paired contrasts print `missing`."),
        ("Pending. ", "all 10 sweep points and all 5 baseline cells."),
    ], size=16.5)
    para(frame, "We would rather show you one honest contrast than eighteen invented ones.",
         size=15, italic=True, color=AMBER, space_before=10, space_after=0)
    notes(slide, "5:00–5:45. Say this before the results, not after. The point is that the "
                 "aggregation refuses to fill a missing cell, so the report and the deck cannot "
                 "drift from the runs.")

    # 7 — matrix results
    slide = slide_frame(prs, "The one contrast we can measure", "Results · retrieval")
    picture(slide, "fig1-intervals.png", Inches(0.5), None, Inches(7.85))
    frame = textbox(slide, Inches(8.75), Inches(1.62), Inches(4.0), Inches(4.9), anchor=MSO_ANCHOR.MIDDLE)
    para(frame, "hybrid − dense", size=14, bold=True, color=ACCENT, first=True, space_after=8)
    for value, label in (("+5.0 pt", "hit@10"), ("+17.1 pt", "MRR"), ("+7.5 pt", "citation recall")):
        paragraph = frame.add_paragraph()
        paragraph.space_after = Pt(6)
        run = paragraph.add_run()
        run.text = value + "   "
        run.font.size = Pt(16)
        run.font.bold = True
        run.font.color.rgb = AMBER
        run.font.name = BODY_FONT
        run = paragraph.add_run()
        run.text = label
        run.font.size = Pt(13)
        run.font.color.rgb = INK
        run.font.name = BODY_FONT
    para(frame, "Every interval overlaps. No paired test exists yet, because no contrast has both "
                "ends. This is a direction, not a result.", size=13, color=MUTED,
         space_before=8, space_after=0, line=1.05)
    notes(slide, "5:45–7:00. Run ids: grid-fixed-hybrid-plain-20261030T125429-6170ae66 and "
                 "grid-fixed-dense-plain-20261030T124637-8ae4eb06. Numbers: 0.9000 vs 0.8500 "
                 "hit@10 with CIs [0.8000,0.9750] vs [0.7250,0.9500]; MRR 0.6529 vs 0.4817; "
                 "citation recall 0.9500 vs 0.8750. Say the limitation sentence before anyone "
                 "asks. Source reports/significance.csv.")

    # 8 — abstention
    slide = slide_frame(prs, "Abstention: a rank-fusion score is not a confidence", "Results · abstention")
    picture(slide, "fig2-abstention.png", Inches(0.55), None, Inches(8.0))
    frame = textbox(slide, Inches(8.7), Inches(1.65), Inches(4.05), Inches(4.9))
    bullets(frame, [
        ("18-point sweep.", "Working point fixed before the numbers: max F1 subject to "
         "over-abstention ≤ 0.05."),
        ("rerank → raw 0.759250.", "precision 0.714, recall 1.000, under-abstention 0.400."),
        ("hybrid plateau.", "2 answerable items and 5 near-misses all score 0.032522 — a "
         "0.000265 gap decides them together."),
    ], size=13.5, gap=7)
    para(frame, "In the matrix cells the tuned threshold never fires: 0.20 vs an observed 0.658, "
                "0.01 vs 0.032. Every abstention there is the generator's own refusal.",
         size=12.5, color=AMBER, space_before=6, space_after=0, line=1.05)
    notes(slide, "7:00–8:15. Runs: real-rerank-20261030T095541-a6eb2d5e, "
                 "real-hybrid-20261030T092148-08d22872; working points in "
                 "reports/abstention/working-points.json. The honest caveat is the amber line: "
                 "the numbers in the matrix measure the generator, not the tuned operating point.")

    # 9 — error taxonomy
    slide = slide_frame(prs, "Fourteen failures, and ten of them are retrieval", "Diagnosis")
    picture(slide, "fig3-error-classes.png", Inches(0.55), None, Inches(7.7))
    frame = textbox(slide, Inches(8.4), Inches(1.6), Inches(4.35), Inches(5.0))
    bullets(frame, [
        ("6 document misses.", "`docs/concepts/seal` never retrieved in either cell; an overview "
         "page's paraphrase satisfies the surface match."),
        ("4 chunk misses.", "Right document, wrong chunk — the failover paragraph sits in a "
         "sibling chunk."),
        ("A015 changes class.", "Over-abstention under dense, chunk miss under hybrid: exactly the "
         "delta contextualisation should produce."),
    ], size=13.5, gap=7)
    para(frame, "That is why the contextualisation column is the first to run.",
         size=13, italic=True, color=AMBER, space_before=6, space_after=0, line=1.05)
    notes(slide, "8:15–9:00. Short: the taxonomy routes the next experiment. 14 failures from 18 "
                 "candidates across the two cells, assigned by the earliest layer that lost the "
                 "answer (notes/error-taxonomy.md). Ten of 14 are retrieval; the other five are a "
                 "parse failure, two over-abstentions and one fabricated span.")

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
    notes(slide, "9:00–11:30. DEMO. Type the question, do not just talk over the screen. Order: "
                 "A001, A007, A009, U008. If the model is slow, fall back to the cache replay and "
                 "say you are doing it. Keep the U008 explanation for last: 0.669 is above the "
                 "threshold, so the refusal is the generator's, which is the honest story. "
                 "Script and captured outputs: notes/demo-script.md.")

    # 11 — cost
    slide = slide_frame(prs, "Long context is not the expensive baseline", "Cost")
    picture(slide, "fig4-prompt-shape-cost.png", Inches(0.55), None, Inches(7.8))
    frame = textbox(slide, Inches(8.45), Inches(1.6), Inches(4.3), Inches(5.0))
    bullets(frame, [
        ("¥4.77 vs ¥9.54.", "A 20,000-character document cap costs half the reference cell's "
         "8-pasted-chunks prompt."),
        ("What it costs is the handle.", "No chunk ids in the prompt, so claims cite a doc id and "
         "land as `chunk_not_retrieved`."),
        ("Measured: ¥8.46/1k.", "hybrid cell, 387,766 prompt + 29,952 completion tokens."),
    ], size=13.5, gap=7)
    para(frame, "So we do not argue that long context is too expensive. It is not.",
         size=13, italic=True, color=AMBER, space_before=6, space_after=0, line=1.05)
    notes(slide, "11:30–12:30. This slide exists to kill an argument we could have made and would "
                 "have been wrong about: projections from reports/baselines/window-cost.json have "
                 "an 8% error bar and the gap is 3×. Generator probe too if asked: gpt-6-luna "
                 "¥6.80 vs ¥9.54 per 1,000, a 29% saving, 19 probe requests for $0.0017.")

    # 12 — threats
    slide = slide_frame(prs, "What is not established", "Limits")
    frame = textbox(slide, Inches(0.62), Inches(1.6), Inches(11.3), Inches(5.0))
    bullets(frame, [
        ("Two cells.", "Main effects rest on one or two cells per level; interactions and all nine "
         "contrasts are unestimated."),
        ("No human read the golden set.", "`verified_by: automated:corpus-anchored` — quotes proven "
         "verbatim and unique, questions drafted from sentences read in context, but grading "
         "behaviour unverified."),
        ("Citation numbers are containment.", "No matrix cell ran the judge, so precision means "
         "“the span occurs”, not “the citation supports the claim”."),
        ("Latency is cache-dominated.", "61 of 64 LLM calls in the dense cell were cache hits: "
         "17.3 ms is a SQLite read, not a round trip."),
        ("14 failures, not 40.", "The ticket asked for 40 hand-inspected; two cells contain 14 and "
         "we did not pad the table."),
    ], size=15.5, gap=7)
    notes(slide, "12:30–13:30. Read these as commitments, not apologies: each is one line in the "
                 "report's threats-to-validity section, and each names the experiment that would "
                 "fix it.")

    # 13 — what next
    slide = slide_frame(prs, "With more time, in the order the taxonomy justifies", "Next")
    frame = textbox(slide, Inches(0.62), Inches(1.6), Inches(11.4), Inches(5.0))
    steps = [
        ("1  Finish the 16 cells — contextualisation column first.",
         "It is where the largest diagnosed class can move, and a null result there is informative."),
        ("2  Run the ten sweep points.",
         "The chunk-size curve is the cleanest answer to the brief's chunking comparison; the hop "
         "curve decides whether the loop earns its rewrite calls."),
        ("3  Parent-chunk generation.",
         "`parent_id` already travels through retrieval; citing the child while reading the parent "
         "needs one span field, not a re-index (ADR-0017)."),
        ("4  Judge-enabled headline cells.", "So citation precision stops meaning containment."),
        ("5  A human reads the 60 items.", "The one threat no compute removes."),
        ("6  Write the per-mode threshold back.", "So abstention measures the operating point it claims to."),
    ]
    for lead, rest in steps:
        paragraph = frame.paragraphs[0] if lead.startswith("1") else frame.add_paragraph()
        paragraph.space_after = Pt(9)
        run = paragraph.add_run()
        run.text = lead
        run.font.size = Pt(15)
        run.font.bold = True
        run.font.color.rgb = ACCENT
        run.font.name = BODY_FONT
        run = paragraph.add_run()
        run.text = "  " + rest
        run.font.size = Pt(14)
        run.font.color.rgb = INK
        run.font.name = BODY_FONT
    notes(slide, "13:30–14:30. One line per item, no elaboration beyond the first. The order is the "
                 "taxonomy's, not ours: the class that the next factor can move comes first.")

    # 14 — close
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(1, Emu(0), Inches(2.0), W, Inches(3.1))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    band.shadow.inherit = False
    frame = textbox(slide, Inches(0.75), Inches(2.35), Inches(11.9), Inches(2.4))
    para(frame, "Grounded or silent — and both are measured.", size=30, bold=True, color=WHITE,
         first=True, space_after=12, line=1.05)
    para(frame, "90.0% hit@10 · 95.0% citation recall · 20/20 near-misses refused · "
                "¥8.46 per 1,000 questions", size=15, color=RGBColor(0xC9, 0xD6, 0xE2),
         space_after=0)
    frame = textbox(slide, Inches(0.75), Inches(5.4), Inches(11.9), Inches(1.6))
    para(frame, "Questions — and the contribution page is the last page of the report.",
         size=14, color=INK, first=True, space_after=6)
    para(frame, "Code: `ragqa/` · artifacts: `reports/` · decisions: `docs/adr/0001`–`0017` · "
                "brief requirements 1–5 mapped in §1", size=12.5, color=MUTED, space_after=0)
    notes(slide, "14:30–15:00. Close on the two-word contract: grounded or silent. Leave the four "
                 "numbers up while questions run. If asked for the weakest number, it is the "
                 "absence of a paired test, not the accuracy.")

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
