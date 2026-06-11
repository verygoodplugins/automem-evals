# Session 2026-06-11 — Negative-control probes (recall_cleanup_v2)

## What we tried

Closed the gap noted in `data/results/SUMMARY-20260417.md` ("Add scenarios where
the correct answer is nothing relevant to measure over-retrieval"): added
`scenarios/recall_cleanup_v2.json`, a strict superset of v1 (all 22 probes
byte-identical) plus five `"group": "negative"` probes, and taught
`compare_recall_endpoints.py` to classify them.

## Probe designs

| ID | Axis |
|---|---|
| `NEG-SCOPED-OFFTOPIC-130` | automem#130 replica — on-corpus topic (the `BUGFIX-D1-SYNC` query verbatim) gated to the unrelated existing tag `moltbook-engagement`. Today this returns confident off-topic results; after the server's relevance gate (automem `fix/130-relevance-gate`) it should return few/none. |
| `NEG-PREFERENCE-TOPIC-ABSENT` | `tags: ["preference"]` with a topic that has no preference memories |
| `NEG-OFFDOMAIN-COOKING` | off-domain query, no tag gate |
| `NEG-NONEXISTENT-ENTITY` | synthetic person/project absent from the corpus |
| `NEG-ABSENT-STACK` | plausible-but-absent tech stack (embedding near-neighbor leakage) |

## Runner semantics

`classify_status` for `negative` probes: REGRESSION when the candidate returns
*more* results or a *higher* top-1 `final_score` than baseline (regression
checks run before improvement checks — a more-confident false positive is the
worse failure for a negative control); `improved` on fewer results or lower
top-1 score; `ok` otherwise. `diff_summary` now records
`top1_score_baseline`/`top1_score_candidate` for every probe.

Note: negative REGRESSIONs are report-only — the `--fail-on-preserve-*` exit
gates still inspect only `preserve` probes. A `--fail-on-negative-regression`
flag is a cheap follow-up if the #130 rollout wants a hard gate.

## What we found

Schema observation: probes carry no expectations field; the group label is the
entire contract, consumed only by `classify_status`. Preflight warm-up selects
preserve probes first, so legitimately-empty negative probes cannot trip the
"warm-up returned no results" failure.

These probes are the measurement instrument for the AutoMem relevance-gate
change (`RECALL_RELEVANCE_GATE`): run the two-stack A/B with gate=0 vs a
candidate gate value and expect `NEG-SCOPED-OFFTOPIC-130` to move from
high-scoring garbage to `improved`, with zero deltas on all 9 preserve probes.
