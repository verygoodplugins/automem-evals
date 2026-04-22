# Session 2026-04-23 — V1 failure-mode forensics

## Inputs

- Baseline: `data/results/beam/20260421-234814-100K-0_19/beam_results_20260422_035020.json` (171MB, 400 questions, V1 shim, gpt-5-mini both)
- 95 FAIL-judged questions extracted: `.../failures_v1.json`
- Classifier output: `.../failures_v1_classified.json` (gpt-5-mini, 27.8s, ~$0.20)

## Taxonomy (locked before classification)

| Bucket | Name | V2 expected to help? |
|---|---|---|
| A | retrieval_miss — ground-truth chunk not in top_100 | **Yes** (smaller atomic memories rank better) |
| B | chronology_confusion — right chunk retrieved but old+new fact both in it, answer picks old | **Strongly yes** (extraction separates facts, enables `INVALIDATED_BY` edges) |
| C | answerer_ignored — right fact cleanly in top_memories, answer ignores it | **No** (answerer-side) |
| D | no_ground_truth — retrieval has nothing; corpus/ingestion gap | **Incidentally** (extraction bypasses 50K cap) |
| E | hallucination_or_no_abstain — answer fabricated / failed to abstain | **No** (answerer-side) |
| F | other | — |

## Overall distribution (n=95)

| Bucket | Count | % | V2 targets? |
|---|---|---|---|
| A | 47 | 49.5% | ✔ |
| B | 8 | 8.4% | ✔✔ |
| C | 25 | 26.3% | ✘ |
| D | 0 | 0.0% | — |
| E | 15 | 15.8% | ✘ |
| F | 0 | 0.0% | — |

**Roughly 58% of all failures are V2-addressable** (A+B), **42% are not** (C+E).

## Per-category distribution

| Category | A (miss) | B (chrono) | C (ignored) | E (hallu) | A+B | V2 leverage |
|---|---:|---:|---:|---:|---:|---|
| **knowledge_update** (n=17) | 11 | 5 | 1 | 0 | **94%** | **High** |
| event_ordering (n=12) | 9 | 0 | 3 | 0 | 75% | High |
| temporal_reasoning (n=11) | 8 | 1 | 2 | 0 | 82% | High |
| multi_session_reasoning (n=12) | 10 | 0 | 1 | 1 | 83% | High |
| contradiction_resolution (n=4) | 1 | 2 | 1 | 0 | 75% | High |
| information_extraction (n=1) | 1 | 0 | 0 | 0 | 100% | Low (already 97.5%) |
| instruction_following (n=4) | 2 | 0 | 2 | 0 | 50% | Medium |
| summarization (n=14) | 4 | 0 | 10 | 0 | 29% | **Low** |
| preference_following (n=2) | 0 | 0 | 2 | 0 | 0% | **None** |
| abstention (n=18) | 1 | 0 | 3 | 14 | 6% | **None** |

## Phase-2 gate decision

**Pre-committed rule:** proceed with V2 only if ≥60% of `knowledge_update` failures are A or B.

Observed: **16/17 = 94%**. ✅ **Proceed to V2.**

## Predicted V2 deltas (pre-run)

These are my best calibrated guesses *before* running V2, so I can't post-rationalize later. Each is ±5pp.

| Category | V1 pass | Predicted V2 pass | Why |
|---|---:|---:|---|
| knowledge_update | 57.5% | **72–78%** | 16/17 failures are A/B; extraction should fix most |
| event_ordering | 70.0% | 75–80% | Many A failures; atomic memories rank better; no B to fix |
| temporal_reasoning | 72.5% | 77–82% | Similar — mostly A |
| multi_session_reasoning | 70.0% | 73–77% | Mostly A, but 1 E bounds the gain |
| contradiction_resolution | 90.0% | 88–92% | Already near ceiling; small sample; could go either way |
| information_extraction | 97.5% | 95–98% | At ceiling, V2 could even hurt slightly if fact extraction misses details |
| instruction_following | 90.0% | 88–92% | Even split A/C; wash |
| summarization | 65.0% | 62–68% | **C-dominated** (10/14) — V2 won't help; could hurt via extraction losing context |
| preference_following | 95.0% | 92–97% | Only 2 fails; already near ceiling; could drop slightly |
| abstention | 55.0% | 53–58% | **E-dominated** (14/18) — answerer problem, V2 won't help |
| **overall** | **76.25%** | **78–82%** | 58% of failures addressable; expect modest but real gain |

## Secondary findings

### The D bucket is empty

Zero of 95 failures were classified as no_ground_truth. That is, the judge's failure mode is *never* "we just don't have the fact" — every failure has retrieval context to work from or has a fact that *should* be retrievable.

This is evidence the V1 shim's 50K truncation warnings on conversations 3 and 4 did **not** materially cost us on this bucket. Those chunks got sliced but the questions scored against them didn't expose the loss. Worth remembering: the "truncation" concern in the V1 baseline is real but did not manifest as scoring damage at 100K. It may manifest at 1M where chunks are larger and diverse.

### Summarization's C pattern is real and answerer-side

10 of 14 summarization failures have the correct facts in the top memories but the generated answer drifts, over-generalizes, or cherry-picks — a "focus" problem, not a retrieval problem. V2 is irrelevant here. Fixing summarization would require prompt-engineering on the answerer or changing the upstream prompt template — both out of scope for tonight.

### Abstention's E pattern = answerer over-confidence

14 of 18 abstention failures have the answerer confidently fabricating specifics when the right answer is "no information available." This is fundamentally an answerer-prompt issue. The V1 shim currently stores raw dialogue that contains plausible-sounding detail across other sessions — when asked about a specific thing that never happened, the answerer confabulates from thematically similar context.

V2 might *marginally* help here by making fact retrieval more precise (fewer thematic-but-wrong hits), but the bucket's dominance by E suggests the bigger lever is the answerer prompt telling it to abstain when nothing directly matches.

## What Phase 2 needs to produce

Given the above, V2 extraction must:

1. **Split atomic facts from raw dialogue** — the primary A-fix. If a conversation chunk has "I have 2 kids" and "I run marathons," those become two separate memories, each independently retrievable. Current V1 stores a single blob keyed on the whole chunk's embedding.
2. **Make chronology edits extractable** — for B. If the user says "I used to work at X, now I work at Y" in one turn, extraction must produce both facts (ideally with temporal markers) so that downstream retrieval can privilege the more recent one. AutoMem's `INVALIDATED_BY` edge is the mechanism IF we give it the signal.
3. **Preserve the user_id tag** so BEAM's cross-conversation isolation still holds.
4. **Stay cheap** — running gpt-4o-mini on every ingestion chunk adds a few dollars across the full bucket, but it's a small price for A+B addressability.

Mem0's `FACT_RETRIEVAL_PROMPT` (pinned at `runners/prompts/mem0_prompts_daa4495.py`) is exactly this. Not reinventing the wheel — using their actual prompt verbatim so the V2 shim delivers the same structural input to AutoMem that mem0 gives itself.

## Caveats

- **gpt-5-mini classifier**, not human adjudication. Confidence is calibrated enough for a gate decision but individual mis-classifications surely exist. Spot-check before acting on single-question findings.
- **Sample size per category is small** — `contradiction_resolution` has only 4 failures; the pattern estimate for it is weak.
- **No distinction between "ranking failure" and "retrieval miss"**: both currently bucket to A. A dedicated second-pass classifier could separate them, but the V2 implication is the same either way.

## Next

→ Phase 2: build `runners/beam_shim_v2.py` using mem0's pinned extraction prompt. Smoke on 2 convs before committing 3h.
