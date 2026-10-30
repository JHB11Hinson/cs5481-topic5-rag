# Judge agreement

- hand-labelled calibration set: 30 claims (20 labelled supported) at `notes\judge-calibration.json`
- NLI layer: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`
- judge layer: `deepseek-v4-pro`
- agreement bar: kappa >= 0.60
- **layer that gates reporting: judge**

Kappa is recomputed from the stored verdicts and the hand labels, not copied from `judge-calibration.metrics.json`. A layer under the bar is reported as advisory and cannot be the gate.

| layer | n | skipped | agreement | precision | recall | kappa | >= bar | role |
|---|---|---|---|---|---|---|---|---|
| containment | 30 | 0 | 0.6667 | 0.6667 | 1.0000 | 0.0000 | no | advisory |
| nli | 30 | 0 | 0.8333 | 0.8261 | 0.9500 | 0.5946 | no | advisory |
| judge | 30 | 0 | 0.9333 | 1.0000 | 0.9000 | 0.8571 | yes | gates reporting |

## NLI x judge confusion

| table | cell | count |
|---|---|---|
| nli_x_judge | both_supported | 18 |
| nli_x_judge | nli_only | 5 |
| nli_x_judge | judge_only | 0 |
| nli_x_judge | neither | 7 |
| nli_vs_human | tp | 19 |
| nli_vs_human | fp | 4 |
| nli_vs_human | fn | 1 |
| nli_vs_human | tn | 6 |
| judge_vs_human | tp | 18 |
| judge_vs_human | fp | 0 |
| judge_vs_human | fn | 2 |
| judge_vs_human | tn | 10 |

`nli_only` is the cell that matters: claims the entailment model passes and the judge rejects are where a cheap layer would have let a bad citation through.

## Confusion recorded inside run directories

No finished cell ran with the judge enabled, so `grounding.judge_confusion` is absent from every run directory. The calibration set above is the only judge evidence in this snapshot.

