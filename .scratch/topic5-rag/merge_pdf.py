"""Concatenate `reports/report.pdf` and `reports/slides.pdf` into `reports/submission.pdf`.

The brief wants the slides appended at the end of the report, with the contribution
page as the last page of the main report — i.e. the page immediately before the
slides. Appending preserves exactly that order.

    python .scratch/topic5-rag/merge_pdf.py
"""

from __future__ import annotations

import pathlib

import fitz

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "report.pdf"
SLIDES = ROOT / "reports" / "slides.pdf"
OUT = ROOT / "reports" / "submission.pdf"


def main():
    out = fitz.open()
    for source in (REPORT, SLIDES):
        with fitz.open(source) as handle:
            out.insert_pdf(handle)
    out.set_metadata(
        {
            "title": "A Documentation Knowledge Base That Cites What It Says, "
                     "and Says Nothing When It Cannot",
            "subject": "CS5481 Data Engineering — Topic 5 group project report, slides appended",
            "author": "CS5481 Topic 5 group",
            "keywords": "RAG, citations, abstention, Vault documentation, CS5481",
        }
    )
    out.save(OUT, garbage=4, deflate=True)
    out.close()

    with fitz.open(OUT) as handle:
        report_pages = fitz.open(REPORT).page_count
        slide_pages = fitz.open(SLIDES).page_count
        print(f"report {report_pages} pp + slides {slide_pages} pp = {handle.page_count} pp")
        last_main = handle[report_pages - 1].get_text()
        print("last page before the slides starts with:", last_main.splitlines()[0][:60])
        print("first slide page starts with:", handle[report_pages].get_text().splitlines()[0][:60])


if __name__ == "__main__":
    main()
