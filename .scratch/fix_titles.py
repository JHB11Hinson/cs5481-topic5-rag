"""Show "New chat" instead of the store's "Untitled conversation" placeholder."""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("ragqa/niceui.py")
HELPER = '''def _display_title(title: Optional[str]) -> str:
    """The store calls an unnamed conversation "Untitled conversation"; a chat product
    says "New chat". One mapping, applied wherever a title is shown."""
    text = (title or "").strip()
    if not text or text == "Untitled conversation":
        return "New chat"
    return text


'''

REPLACEMENTS = [
    ('self.title_label.text = record.get("title") or "New chat"',
     'self.title_label.text = _display_title(record.get("title"))'),
    ('title = _escape(row["title"] or "New chat")',
     'title = _escape(_display_title(row.get("title")))'),
    ('ui.label(record.get("title") or "New chat").classes("text-sm font-semibold")',
     'ui.label(_display_title(record.get("title"))).classes("text-sm font-semibold")'),
]


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
            print(f"replaced: {old[:60]}")
        else:
            print(f"not present (skipped): {old[:60]}")
    if "def _display_title(" not in text:
        text = text.replace("def _escape(text: str) -> str:", HELPER + "def _escape(text: str) -> str:", 1)
        print("helper inserted")
    with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
