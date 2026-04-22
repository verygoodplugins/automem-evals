# Session 2026-04-23 — Overnight strategy (apples-to-apples)

## Guiding principle

Not "beat mem0." The goal is using BEAM to expose *where AutoMem is structurally weaker and why*, so those findings feed back into AutoMem. The cleanest way to do that is to give AutoMem the same structural input mem0 gives itself — pre-extracted facts, not raw dialogue — and see which of AutoMem's weak spots close.

## Hypothesis under test

**The V1 shim skips fact extraction, which is probably why `knowledge_update` scores 57.5% vs mem0's 75–80%.** mem0-OSS runs every message batch through `gpt-4o-mini` to extract atomic facts before writing to its vector store; AutoMem's V1 shim concatenates raw turns and stores one blob. A supersession graph (AutoMem's `INVALIDATED_BY` edge) can't fire on dialogue blobs — it needs fact-level units to compare.

If this is right, V2 with fact extraction should materially improve `knowledge_update` (primary signal) and `contradiction_resolution` at larger tiers (secondary signal — V1 is already 90% at 100K so headroom is capped). If V2 doesn't move the needle, the gap lives elsewhere — likely in AutoMem's recall ranking or the answerer's use of retrieved context.

## Phase plan

Each phase is gated on the prior; cheap/diagnostic work happens first, expensive runs only if upstream results justify them.

### Phase 1 — Failure-mode forensics (V1 baseline)
- **Cost:** $0, time ~45min
- **Inputs:** `data/results/beam/20260421-234814-100K-0_19/beam_results_20260422_035020.json` (171MB)
- **Output:** `docs/session_20260423_failure_modes.md`
- **Method:** Extract the 95 failed questions. Per category, sample and classify:
  - (a) *retrieval-miss* — the right memory was not in the top-k retrieval
  - (b) *ranking-failure* — the right memory was retrieved but ranked below distractors
  - (c) *answerer-ignored* — right memory was in context but answer chose a wrong fact
  - (d) *no-ground-truth* — the corpus never contained the needed fact (ingestion bug or data issue)
  - (e) *hallucination / abstention-failure* — answerer fabricated or refused to abstain
- **Why this first:** tells me what V2 fact extraction needs to optimize for. If most V1 failures are (c) or (d), fact extraction helps. If most are (b), V2 won't help and we should instead look at recall ranking.

### Phase 2 — V2 extraction shim
- **Cost:** cents (smoke test only); dev time ~2hr
- **Output:** `runners/beam_shim_v2.py`, smoke-tested on 2 convs
- **Design:** Before `POST /memory`, call `gpt-4o-mini` on the messages with a prompt that mirrors mem0-OSS's extraction (see `third_party/memory-benchmarks` upstream if we can locate the prompt, else replicate). Extract atomic facts; store each as a separate AutoMem memory under the same `user_id` tag. Side benefit: each extracted fact is small, so the 50K truncation issue that bit conversations 3 and 4 in the V1 baseline goes away.
- **Add:** `--shim-version {v1,v2}` flag to `runners/run_beam.py` so the two can co-exist.
- **Exit criterion:** 2-conv smoke returns valid `beam_results_*.json`, fact-extraction produces plausible outputs, ingestion rate is not worse than 3× V1 (gpt-4o-mini is fast; this should be fine).

### Phase 3 — V2 full bucket at 100K
- **Cost:** ~$5 (gpt-5-mini answerer + gpt-5-mini judge, matches V1 baseline exactly for clean delta)
- **Time:** ~3h wall-clock
- **Output:** `data/results/beam/<ts>-100K-0_19-v2/`, plus `docs/session_20260423_v1_vs_v2.md` with per-category delta table
- **Judge call:** gpt-5-mini both, same as V1 baseline, because the target is V1→V2 delta, not v mem0. Judge noise cancels in diff.
- **Gate for Phase 4:** if V2 moves `knowledge_update` by ≥10pp in the expected direction, proceed to 1M. Otherwise write up the null result and stop.

### Phase 4 (conditional) — 1M apples-to-apples
- **Cost:** ~$20 (gpt-5 judge is the premium call — ~$15, gpt-5-mini answerer ~$5)
- **Time:** ~4h wall-clock
- **Subset:** first 7 convs (0-6) at 1M tier, ~140 questions. Same subset size mem0's published 1M column used per category — direct comparison possible per category at n=~14.
- **Judge:** gpt-5 (to match mem0's published config — this is the real apples-to-apples)
- **Output:** `docs/session_20260423_1M_comparison.md` with per-category side-by-side vs mem0's 1M top_200 column.

### Phase 5 — Final insights
- Consolidate Phases 1–4 into `docs/session_20260423_overnight_insights.md`.
- Promote durable findings into project memory via `mcp__memory__store_memory` (with `automem-evals` tag).
- Update `docs/session_20260422_beam_fullbucket.md` with "Phase 2 follow-up" cross-references.

## Budgets

| Phase | Est $ | Est h |
|---|---|---|
| 1 Forensics | 0 | 0.75 |
| 2 V2 shim build | <1 | 2 |
| 3 V2 100K full | 5 | 3 |
| 4 1M apples-to-apples | 20 | 4 |
| 5 Writeup | 0 | 0.5 |
| Total | ~26 | 10.25 |

Tight for 8h. If Phase 2 drags (fact-extraction prompt tuning) I'll cut Phase 4 and deliver a sharp V1→V2 writeup instead of a broad apples-to-apples.

## Non-goals tonight

- Building the regression harness (`beam_diff.py`, `--regression-preset`). That's the *next* session; tonight's priority is producing the actual baselines the harness will compare.
- LoCoMo / LongMemEval. Same reason.
- Tuning the answerer or the judge. Variables held constant.
- Any changes to AutoMem itself. This is eval-side work only.

## Checkpoints (soft)

- **2h in:** Phase 1 doc exists, V2 shim has a first-draft + smoke started.
- **4h in:** V2 shim smoke is green, V2 full bucket kicked off.
- **7h in:** V2 full bucket done, V1 vs V2 doc written, Phase 4 decision made.
- **8h:** Final insights doc exists (even if Phase 4 didn't run).
