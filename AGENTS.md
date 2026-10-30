# AGENTS.md

## Project

CS5481 Data Engineering — group project (2026). Topic: **Topic 5 — Knowledge Base Q&A System with Verifiable Citations** (RAG).

- Course brief: `docs/course-brief/CS5481_Project_2026-1.pdf` — the source of truth for every requirement below. Original file lives one level up at `../CS5481_Project_2026-1.pdf`; re-copy it if the brief is updated.
- Group: up to 8 members. Groups are registered on Canvas (People → Groups).
- Deliverables: report + source code via Canvas, plus a 15-minute in-class presentation.
- Report structure: at minimum introduction, methodology, experiments and discussions. Up to 6 pages of main content; references and appendix unlimited.
- Slides are appended to the report. A dedicated contribution page (individual contributions, ratios in %, every member's signature) must be the last page of the main report — the page right before the appended slides — and does not count toward the 6-page limit. A submission missing that page, or any signature, is desk rejected.
- Source code: Jupyter Notebook or Python files.
- Deadline: 2026-11-24 23:59.

### Requirements the brief mandates (do not quietly drop these)

1. **Data preparation** — collect a document set, then load, chunk, and embed it. Compare at least two chunking strategies (e.g. different chunk sizes, overlapping vs. non-overlapping) and report their impact on retrieval quality.
2. **Knowledge base storage** — store chunks and their embeddings in a vector database.
3. **Retrieval** — embed the user's question, retrieve the most relevant chunks by semantic similarity.
4. **Grounded answer generation** — pass question plus retrieved chunks to an LLM, prompt it to answer only from that context and cite the source document (and chunk) for each claim; if the knowledge base does not contain the answer, say so explicitly instead of guessing.
5. **Evaluation** — build a test set of at least 20 question-answer pairs and report retrieval hit rate and answer correctness.

### Not decided yet

Document domain, real-world application scenario, tech stack, embedding model, vector database, LLM provider, chunking parameters, and evaluation metric definitions are all open. Do not assume a choice that is not written down in an ADR or a spec; when a decision is made, record it in `docs/adr/`.

## Conventions

- Everything graded or read by course staff is written in **English**: report, slides, README, code comments, docstrings, commit messages, and anything under `docs/`.
- Chinese is fine for discussion, planning, and scratch notes.
- Never hardcode API keys, model endpoints, or credentials. Read them from environment variables and keep a `.env.example` with placeholder names only.
- Keep experiment results reproducible: record the chunking parameters, model versions, and dataset snapshot behind any number that appears in the report.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles keep their own names as label strings, recorded on a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the repo root and ADRs in `docs/adr/`. See `docs/agents/domain.md`.
