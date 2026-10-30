# 10: Two support judges and their agreement

**What to build:** claims that survive containment are judged for support twice — a local NLI cross-encoder and a hosted model — and the two are calibrated against 30 hand-labelled claims, so the report can state how much either judge can be trusted.

**Blocked by:** 06, 08.

**Status:** ready-for-agent

- [ ] `ragqa verify` adds NLI verdicts and judge verdicts per claim, with the judge's one-line reason stored
- [ ] Citation precision, citation recall, and span hit rate are computed from verdicts, not from the generator's self-report
- [ ] A confusion table between NLI and judge verdicts is emitted
- [ ] `notes/judge-calibration.md` holds 30 hand-labelled claims, Cohen's kappa for each judge against the human, and a stated decision on which layer gates reporting
- [ ] Judge cost and call counts are recorded per configuration
