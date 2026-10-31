"""Route every `ui.html(...)` in niceui.py through one helper.

NiceGUI 3.x makes `sanitize` a required keyword-only argument on `ui.html`, so every
call that omits it raises at page-build time — and because the page builder catches its
own exception to print a message instead of a 500, the whole screen degrades to "The demo
failed to start". One helper is better than a keyword repeated seventeen times, and it
states the rule in one place: this module escapes everything it interpolates, so the HTML
it feeds to the browser is already safe.
"""

from __future__ import annotations

import pathlib
import re

PATH = pathlib.Path("ragqa/niceui.py")
HELPER = '''

def html(content: str) -> ui.html:
    """A `ui.html` that does not need a `sanitize` argument at every call site.

    Everything this module interpolates is escaped by `_escape` or by
    `ChatEngine.citation_props` (which escapes the chunk and wraps the cited span in
    `<mark>`), so re-sanitising would only strip the highlight. One rule, one place.
    """
    return ui.html(content, sanitize=False)

'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")

    # Normalise the one call that already passes the keyword, then rewrite the rest.
    text = text.replace('ui.html("", sanitize=False)', 'html("")')
    calls = len(re.findall(r"(?<![\w.])ui\.html\(", text))
    text = re.sub(r"(?<![\w.])ui\.html\(", "html(", text)

    if "def html(content: str) -> ui.html:" not in text:
        marker = "def _store() -> history_mod.ConversationStore:"
        if marker not in text:
            raise SystemExit("anchor for the helper not found")
        text = text.replace(marker, HELPER.strip() + "\n\n\n" + marker, 1)

    with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"rewrote {calls} ui.html call(s) through html(); helper inserted once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
