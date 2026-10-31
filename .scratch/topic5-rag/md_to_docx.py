"""Render `reports/report.md` to `reports/report.docx`.

The markdown is the source of truth; this script is the renderer. It understands
the subset of markdown the report actually uses:

    # Title                       big centred title
    **subtitle line**             centred bold metadata line
    ## / ### headings             Heading 1 / Heading 2
    paragraphs                    justified, 9.5 pt
    - item                        bullet
    1. item                       numbered reference entry, hanging indent
    | a | b |                     pipe table, first row header
    ![](path)                     centred figure, 15.6 cm wide
    *Figure N — caption*          centred italic caption
    <!-- pagebreak -->            page break
    `code` **bold** *italic*       inline runs

Usage, from the repo root:

    python .scratch/topic5-rag/md_to_docx.py reports/report.md reports/report.docx
"""

from __future__ import annotations

import pathlib
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_PT = 9.2
TABLE_PT = 7.2
CODE_PT = 8.2
CONTENT_CM = 17.1
FIGURE_CM = 11.4
INK = RGBColor(0x1F, 0x29, 0x33)
ACCENT = RGBColor(0x1B, 0x3A, 0x5B)

INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)")


def set_cell_margins(table, top=10, bottom=10, left=50, right=50):
    tbl_pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tbl_pr.append(mar)


def add_page_number_footer(section):
    paragraph = section.footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    run.font.size = Pt(8)
    run.font.color.rgb = INK
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    paragraph._p.append(fld)


def style_document(document):
    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(1.95)
    section.right_margin = Cm(1.95)
    section.footer_distance = Cm(0.9)

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(BODY_PT)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = 1.0
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), "Calibri")

    for name, size, before, after in (("Heading 1", 12.0, 9, 3), ("Heading 2", 10.0, 6, 2)):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = ACCENT
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for name in ("List Bullet",):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(BODY_PT)
        style.paragraph_format.space_after = Pt(1.5)
        style.paragraph_format.line_spacing = 1.0

    add_page_number_footer(section)


def add_inline(paragraph, text, size=BODY_PT, bold=False, italic=False, color=INK, mono=False):
    for piece in INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            add_inline(paragraph, piece[2:-2], size=size, bold=True, italic=italic, color=color, mono=mono)
            continue
        if piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            run = paragraph.add_run(piece[1:-1])
            run.bold, run.italic = bold, italic
            run.font.size = Pt(CODE_PT)
            run.font.color.rgb = color
            run.font.name = "Consolas"
            rpr = run._element.get_or_add_rPr()
            rfonts = OxmlElement("w:rFonts")
            for attr in ("w:ascii", "w:hAnsi", "w:cs"):
                rfonts.set(qn(attr), "Consolas")
            rpr.append(rfonts)
            continue
        if piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            add_inline(paragraph, piece[1:-1], size=size, bold=bold, italic=True, color=color, mono=mono)
            continue
        run = paragraph.add_run(piece)
        run.bold = bold
        run.italic = italic
        run.font.size = Pt(CODE_PT if mono else size)
        run.font.color.rgb = color
    return paragraph


def fixed_layout(table, widths_cm):
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    total = OxmlElement("w:tblW")
    total.set(qn("w:w"), str(int(sum(widths_cm) * 567)))
    total.set(qn("w:type"), "dxa")
    tbl_pr.append(total)
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for col, width in zip(grid.findall(qn("w:gridCol")), widths_cm):
            col.set(qn("w:w"), str(int(width * 567)))


def add_table(document, rows, widths=None):
    header, body = rows[0], rows[1:]
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_cell_margins(table)

    if widths is None:
        widths = [CONTENT_CM / len(header)] * len(header)
    fixed_layout(table, widths)
    for index, width in enumerate(widths):
        table.columns[index].width = Cm(width)

    for index, text in enumerate(header):
        cell = table.rows[0].cells[index]
        cell.width = Cm(widths[index])
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        add_inline(paragraph, text, size=TABLE_PT, bold=True, color=ACCENT)
        shade = OxmlElement("w:shd")
        shade.set(qn("w:fill"), "EDF1F5")
        cell._tc.get_or_add_tcPr().append(shade)

    # repeat the header row when a long table is split across pages
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    header_flag = OxmlElement("w:tblHeader")
    header_flag.set(qn("w:val"), "true")
    tr_pr.append(header_flag)

    signature_table = any("signature" in cell.lower() for cell in header)
    for row in body:
        cells = table.add_row().cells
        if signature_table:
            table.rows[-1].height = Cm(1.05)
        for index, text in enumerate(row[: len(header)]):
            cells[index].width = Cm(widths[index])
            paragraph = cells[index].paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            add_inline(paragraph, text, size=9.0 if signature_table else TABLE_PT)
    return table


def auto_widths(rows, floor_cm=1.05):
    """Column widths proportional to a concave function of the longest cell."""
    ncols = len(rows[0])
    weights = []
    for index in range(ncols):
        longest = max(len(row[index]) if index < len(row) else 0 for row in rows)
        weights.append(max(longest, 3) ** 0.62)
    total = sum(weights)
    widths = [CONTENT_CM * weight / total for weight in weights]
    widths = [max(width, floor_cm) for width in widths]
    scale = CONTENT_CM / sum(widths)
    return [width * scale for width in widths]


def convert(md_path: pathlib.Path, docx_path: pathlib.Path):
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    document = Document()
    style_document(document)

    pending_table: list[list[str]] = []
    title_done = False
    in_fence = False

    def flush_table():
        nonlocal pending_table
        if not pending_table:
            return
        rows = pending_table
        pending_table = []
        add_table(document, rows, auto_widths(rows))
        tail = document.add_paragraph()
        tail.paragraph_format.space_before = Pt(0)
        tail.paragraph_format.space_after = Pt(0)
        tail.paragraph_format.line_spacing = Pt(3)
        tail.add_run("").font.size = Pt(3)

    for raw in lines:
        line = raw.rstrip()

        if line.strip().startswith("```"):
            flush_table()
            in_fence = not in_fence
            continue
        if in_fence:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.left_indent = Cm(0.3)
            run = paragraph.add_run(line if line else " ")
            run.font.name = "Consolas"
            run.font.size = Pt(7.6)
            run.font.color.rgb = INK
            rpr = run._element.get_or_add_rPr()
            rfonts = OxmlElement("w:rFonts")
            for attr in ("w:ascii", "w:hAnsi", "w:cs"):
                rfonts.set(qn(attr), "Consolas")
            rpr.append(rfonts)
            continue

        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(set(cell) <= set("-: ") and cell for cell in cells):
                continue
            pending_table.append(cells)
            continue
        flush_table()

        if not line.strip():
            continue

        if line.strip() == "<!-- pagebreak -->":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.add_run().add_break(WD_BREAK.PAGE)
            continue

        image = re.match(r"^!\[\]\((.+)\)$", line.strip())
        if image:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(3)
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run()
            run.add_picture(image.group(1), width=Cm(FIGURE_CM))
            continue

        if line.startswith("# ") and not title_done:
            title_done = True
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after = Pt(2)
            add_inline(paragraph, line[2:], size=16.5, bold=True, color=ACCENT)
            continue

        if line.startswith("## "):
            document.add_heading(line[3:], level=1)
            continue

        if line.startswith("### "):
            document.add_heading(line[4:], level=2)
            continue

        if (
            title_done
            and line.startswith("**")
            and line.endswith("**")
            and line.count("**") == 2
        ):
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_after = Pt(6)
            add_inline(paragraph, line[2:-2], size=9.5, bold=True)
            continue

        if line.startswith("- "):
            paragraph = document.add_paragraph(style="List Bullet")
            add_inline(paragraph, line[2:].strip())
            continue

        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.75)
            paragraph.paragraph_format.first_line_indent = Cm(-0.75)
            paragraph.paragraph_format.space_after = Pt(2)
            add_inline(paragraph, f"{numbered.group(1)}.  {numbered.group(2)}")
            continue

        if line.startswith("*") and line.endswith("*") and line.count("*") == 2:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.space_after = Pt(6)
            add_inline(paragraph, line[1:-1], size=8.0, italic=True)
            continue

        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_inline(paragraph, line.strip())

    flush_table()
    document.save(docx_path)
    return docx_path


if __name__ == "__main__":
    source = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "reports/report.md")
    target = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "reports/report.docx")
    convert(source, target)
    print(f"wrote {target} ({target.stat().st_size} bytes)")
