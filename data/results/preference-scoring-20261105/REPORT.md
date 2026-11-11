# Blinded preference scoring calibration

**Decision: do not change retrieval from this experiment.** A blinded,
evidence-anchored reassessment of the same saved answers did not reproduce the
original judge's apparent advantage for pruning retrieved context. The evidence
does not establish an advantage for either arm.

| Result | Full context | Retrieved support only |
| --- | ---: | ---: |
| Original judge: correct | 15/30 | 18/30 |
| Calibrated: pass | 23/30 | 22/30 |
| Calibrated: fail | 6/30 | 6/30 |
| Calibrated: ambiguous | 1/30 | 2/30 |

For the 27 pairs with two decisive calibrated verdicts, support-only won two,
lost two, and tied 23; three pairs were ambiguous. All five original
discordances became both-pass ties. Fourteen original failures became passes
among the 57 decisive calibrated verdicts; that is a disagreement between
scorers, not proof that each original judgment was wrong.

The sample consists of 30 preference questions and 60 saved answers from the
[reconciled context experiment](../precision-context-20261026/RECONCILIATION.md),
at server revision `fe0d5c3` and harness revision `3eaa1f5`. The original
answer-generation experiment used paid models; this calibration made **zero
new paid provider calls**. It used one local Qwen 3.6 35B A3B scorer, which is
neither human gold nor a validated replacement for the benchmark judge.

The scorer received a single answer, its question and required criteria per
request, without the arm label, original judgment or the other arm. Results
were sealed before unmasking. A separate blind quote check recovered 17
formatting or ellipsis mismatches; three answers remained ambiguous. One
post-unmask inspection found a compound-criterion false positive: the scorer
credited an answer despite acknowledging that it omitted one required part.
The sealed verdict was not changed. Consequently, matching quoted text is not
sufficient to establish that every required condition was satisfied.

The [aggregate record](AGGREGATE.json) captures frozen revisions, aggregate
verdicts and hashes of the local evidence. This publication contains no raw
questions, answers, case-level verdicts or rubrics. The hashed source files are
retained locally and are not included here. The small sample and single scorer
do not establish end-to-end agent success or a production effect.

Next, use privacy-reviewed synthetic scorer regressions to test paraphrases,
missing required clauses and optional examples, then validate any scorer change
on a separate holdout. Only after scorer calibration should a matched
preference-to-answer instruction experiment be used to judge whether available
memory helps an agent answer; keep retrieval, ranking and graph settings fixed.
