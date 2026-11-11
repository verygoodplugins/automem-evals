# Exploratory top-score abstention gate

The previously examined synthetic controls do **not** support choosing a single
global threshold. A threshold can reduce nonempty no-answer responses while
removing many relevant paraphrase results. These are small diagnostic counts,
not a held-out calibration or a measure of agent answer quality.

The table projects an **all-or-none client gate** onto the existing candidate
`4431d20e93ee194ed0749d91934af0219fad7b4f` zero-floor responses. If the top
score is below the threshold, the client discards the whole saved result list;
otherwise it retains that list unchanged. Target@5 is measured against the
retained list, not re-ranked or filtered item by item. For a hypothetical
per-result filter applied to that *same fixed list*, the reported target@5
counts are an upper bound: an individually lower-scoring target could be
removed. They are not a general bound on a fresh server request, which could
generate a different candidate pool or ranking.

| Gate threshold | Identifier target@5 | Paraphrase target@5 | No-answer false-positive rate | Wrong-scope queries with results |
| ---: | ---: | ---: | ---: | ---: |
| 0.00 | 16/16 | 14/16 | 16/16 | 4/4 |
| 0.30 | 16/16 | 7/16 | 11/16 | 0/4 |
| 0.35 | 16/16 | 2/16 | 4/16 | 0/4 |
| 0.40 | 16/16 | 0/16 | 2/16 | 0/4 |
| 0.45 | 0/16 | 0/16 | 1/16 | 0/4 |

At 0.30 and 0.35, 7/16 and 2/16 paraphrase targets respectively remain in
the saved lists after the all-or-none gate; these are upper bounds for
filtering those fixed lists, not measured server `min_score` outcomes.

The thresholds were chosen for diagnosis after the data had already been
examined; do not use this table as a threshold-selection study. All negative
queries are synthetic labels for which no answer exists in the requested
scope. A nonempty response is a false-positive **evidence return**, not proof
that an agent answered incorrectly. Wrong-scope responses in the zero-floor
run were unrelated *in-scope* memories, not foreign-scope leaks. No cross-scope
or inactive-memory leaks were observed in these slices.

The same experiment also ran the server with `min_score=0.4` on 52 queries per
arm. Its observed candidate results match the 0.40 gate table for the
aggregate nonempty, target@1, and target@5 counts; the baseline's observed
0.4 run retained 0/16 identifier targets and 0/16 paraphrase targets, with
2/16 negative and 0/4 wrong-scope queries nonempty. This agreement does **not**
make the gate equivalent to server-side filtering: a different candidate pool,
query or ranking could change the response, and this saved receipt does not
include individual lower-ranked scores. No other live threshold was run.

The [aggregate](aggregate.json) includes baseline and candidate projections,
the actual 0.4 observations, disagreement counts, fixture/revision IDs and raw
input hashes. It contains no questions, result text, query IDs or case-level
outcomes. The two strict API-log audits and raw receipts remain local. Both
arms used local BGE, synthetic fixtures, disabled relation expansion and zero
paid calls. The comparison is exploratory; a new disjoint, realistic holdout
and live matched runs are required before choosing an abstention rule.

Reproduction and exact local receipt paths are in the
[probe instructions](../../../experiments/precision_threshold_probe/README.md).
