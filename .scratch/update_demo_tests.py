"""Move the two demo tests onto the new rendering contract.

The old contract put the machinery on screen: a chunk score, a latency footer, an
`error_class` identifier. A live demo showed why that is wrong — a greeting answered with
`0.021` and a JSON blob. The contract now is: the *screen* carries the answer and a
pointer to the closest page; the *payload* carries the scores, ids and timings. These
tests keep the property that mattered (an abstention still shows what retrieval found,
a lying claim is still not displayed as verified) and move the instrumentation assertions
onto the payload, where the citation panel and the stored transcript read them.
"""

from __future__ import annotations

import pathlib

PATH = pathlib.Path("tests/test_demo.py")

OLD_ABSTAIN = '''    screen = demo.render_answer(response)
    assert demo.ABSTAIN_MESSAGE.split(".")[0].lower() in screen.lower()
    assert best["doc_title"] in screen, "the best chunk is named on screen"
    assert f"{best['score']:.3f}" in screen, "its score is shown next to it"
    assert engine.config_name in screen, "the footer states the configuration served"
'''

NEW_ABSTAIN = '''    screen = demo.render_answer(response)
    assert demo.ABSTAIN_MESSAGE.split(".")[0].lower() in screen.lower()
    assert best["doc_title"] in screen, "the best chunk is still named on screen"
    # The score, the chunk id and the configuration live in the payload now: a reader
    # wants the answer and a pointer, and the machinery only ever belonged in a log.
    assert f"{best['score']:.3f}" not in screen, "no score on screen"
    assert engine.config_name not in screen, "no configuration footer on screen"
    assert response["best_chunk"]["score"] == best["score"]
'''

OLD_LIE = '''    screen = demo.render_answer(response)
    assert "quote_not_in_chunk" in screen
    assert "[1]" not in screen
'''

NEW_LIE = '''    screen = demo.render_answer(response)
    assert "[1]" not in screen, "a claim without a verified quote gets no marker"
    assert claim["text"] not in screen, "the withheld claim is not presented as an answer"
    assert "1 further claim(s) were withheld" in screen
    assert "quote_not_in_chunk" not in screen, "the failure class stays in the payload"
'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    for old, new, label in ((OLD_ABSTAIN, NEW_ABSTAIN, "abstain"), (OLD_LIE, NEW_LIE, "lie")):
        if old not in text:
            raise SystemExit(f"could not find the {label} block to replace")
        text = text.replace(old, new, 1)
    with open(PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("tests/test_demo.py updated to the new rendering contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
