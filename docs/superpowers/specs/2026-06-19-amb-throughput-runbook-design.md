# Design: AMB submission — throughput + evidence runbook

**Date:** 2026-06-19
**Status:** approved-in-principle (3 forks chosen), pending spec review
**Owner:** automem-evals
**Parent plan:** `.claude/plans/here-s-a-self-contained-prompt-validated-hare.md` (AMB leaderboard
submission, v1.0) and the `amb-adapter` worktree's
`docs/superpowers/plans/2026-06-16-amb-leaderboard-contribution.md`. This spec refines the
**execution** of those plans — how to run the Gemini-scored AMB suite fast, safely, and with
defensible statistical evidence — it does not change the submission scope or ship config.

## Goal

Produce the full set of **Agent Memory Benchmark (AMB / `omb`)** results for AutoMem —
Core-3 (LoCoMo, LongMemEval, PersonaMem) + BEAM (100K→10M) — with maximum throughput and
statistical credibility, after losing a run cycle to a Gemini quota wall. Report the public
**triplet** per dataset: **accuracy (± 95% CI) / recall latency / context tokens**.

## Confirmed facts (measured this session, not estimated)

### Workload — question counts from the local datasets
| Dataset / split | Questions (answer calls) |
|---|---|
| LoCoMo `locomo10` | 152 |
| LongMemEval `s` | 500 |
| PersonaMem `32k` | 589 |
| BEAM `100K` / `500K` / `1M` / `10M` | 400 / 700 / 700 / 200 = **2,000** |
| **Total unique questions** | **3,241** |

### Pricing (verified 2026-06)
- Answerer `gemini-3.1-pro-preview`: **$2 / $12** per M tokens in/out (≤200k context).
- Judge `gemini-2.5-flash-lite`: **$0.10 / $0.40** per M — effectively free at this volume.
- Ingestion: **$0 on Gemini** — AutoMem embeds locally via FastEmbed (`BAAI/bge-base-en-v1.5`, 768d).
- No batch discount: the harness times retrieval with synchronous calls, so async batch mode is off.
- Per-question cost ≈ **$0.06–$0.12** (answerer reasoning output dominates; retrieved context is
  bounded ~10–15k tokens at every tier because retrieval depth `k` is fixed — **this is why BEAM 10M
  is cheap on credits**, ~$20 for 200 questions; its cost is local ingest time, not Gemini).

### Budget
| Plan | Cost |
|---|---|
| Single clean pass (everything ×1) | ~$300 |
| Chosen plan (3× scored + 1× big tiers + retry waste) | ~$900 |
| **Preload recommendation** | **$1,500** (full margin; covers optional extra splits) |

### Rate limits — root cause of the last crash
- Gemini 3 Pro **preview** on free/low tier: **~10–50 RPM, ~100+ RPD**. The PersonaMem run died at
  247/589 because it **exhausted the daily request cap (RPD)**, not a rate spike.
- **Tier 1** removes the RPD cap (150–300 RPM). **Tier 2** = **1,000+ RPM**, no daily ceiling.
- Tier 2 takes the rate limit off the table and makes **parallel runs** viable. One residual risk:
  preview models can carry a separate, tighter preview-specific quota regardless of tier — verified
  empirically in the calibration step, not trusted on paper.

### Machine ceiling (this host)
- **137 GB host RAM, 18 cores; Docker allotted 105.9 GiB / 18 CPUs.**
- Per stack: Core-3/100k ≈ 1–3 GB; BEAM-10M ≈ 4–8 GB (~1.7 GB vectors + graph).
- **RAM is not the bottleneck.** 12 small stacks in parallel < 40 GB. The real ceilings are **CPU
  embedding throughput** (shared across concurrent ingests) and **Gemini TPM** — both comfortable.

## Decisions (confirmed)
1. **Harden checkpointing before the big runs** — prevent another total-loss crash.
2. **3× repeats on scored runs (Core-3 + BEAM-100K), 1× on big tiers (500K/1M/10M)** — best
   evidence-per-dollar; report mean ± 95% CI.
3. **Calibrate, then max out parallelism** — measured ceiling, not a guessed cap.

## The four moves

### A — Parallel fan-out by dataset
The AMB provider chooses ports per run, so stacks coexist without collision. Run **Core-3 +
BEAM-100K as 4 concurrent stacks**; with 3× repeats that is up to **12 small stacks at once**
(fits trivially in 105 GB). Wall-clock for the small suite collapses from *sum* to *slowest single
run* (~PersonaMem 589q). The ingest-heavy tiers (500K/1M/10M) run **2–3 in parallel** afterward,
bounded by CPU embedding throughput, not RAM.

### B — Repeat-for-confidence (the "0.1 static" instinct)
Retrieval is deterministic (FastEmbed + fixed AutoMem ranking on a fixed corpus); the Gemini
answerer and judge inject the only run-to-run noise. Running each scored dataset **3×** and
reporting **mean ± 95% CI** converts a bare "82%" into "82% ± X%" — the *more proof* a leaderboard
submission should carry. Big tiers run 1× and inherit the CI argument from the cheaper tiers
(same per-question judge-noise distribution).

### C — Calibrate-then-commit
Before the big spend: a **20-question slice per dataset** to (1) confirm Tier 2 has no hidden
preview cap, (2) read **real token usage from Gemini response metadata** and replace the ±2×
estimate with a measured ±10% $/q, (3) measure RAM + CPU per stack to set the parallelism ceiling.
Cost ≈ $5, ~30 min. Commit the $1,500 knowing the exact burn.

### D — Harden checkpointing
The `omb` harness writes results only at the end of a run; a crash discards the partial (this is
what cost us PersonaMem at 247/589). Change: **append per-question results incrementally** and make
the provider/runner **resume from a partial output file** (skip already-answered questions). This is
the single highest-leverage protection and is done **before** any multi-hour 1M/10M run.

## Execution sequence
1. **C — Calibrate** (`--query-limit 20` per dataset): pipeline confirm on Tier 2, measured $/q,
   measured RAM/CPU per stack → freeze the parallelism ceiling.
2. **D — Harden checkpointing**: incremental result append + resume; unit-test the resume path.
3. **A+B — Small suite in parallel, ×3**: LoCoMo, LongMemEval, PersonaMem-32k, BEAM-100K as
   concurrent stacks, 3 repeats each → mean ± 95% CI.
4. **Big tiers, 1× each, 2–3 parallel**: BEAM 500K → 1M → 10M (10M cheap on credits, slow on ingest).
5. **Report**: per dataset, the triplet — **accuracy (mean ± 95% CI) / recall latency (ms, median
   + p95) / context tokens (median)** — into the committed `outputs/` + a results summary.

## Reporting format
For every dataset/tier, never quote accuracy alone:
```
<dataset>/<split>:  acc <mean>% ± <ci>%  (n=<repeats>)  |  recall <median>ms / p95 <p95>ms  |  ctx <median> tok
```
This matches the public AMB triplet and is the head-to-head AutoMem can win on latency + tokens
even where judge-confounded accuracy is only competitive.

## Out of scope (parked, v1.x)
- Maturation / consolidation on a narrative clock (blocked on AutoMem `/consolidate reference_time`).
- A/B of unvalidated ranking flags beyond the frozen ship config (`RECALL_RECENCY_BIAS=auto`).
- Publishing the public GHCR image, fork, and the PR to vectorize-io — **human-gated**, outward-facing.

## Risks
- **Hidden preview quota** on `gemini-3.1-pro-preview` despite Tier 2 → mitigated by step 1 calibration.
- **CPU contention** when many stacks ingest simultaneously → measured in step 1; cap concurrent
  *ingests* (not total stacks) if embedding throughput saturates.
- **10M ingest wall-clock** (984 MB to embed) → run 10M last, alone or paired, overnight if needed.
- **Repeat-run nondeterminism source**: if AutoMem enrichment is LLM-based the graph varies per run
  (more reason to repeat); if rule-based, only answer/judge vary. Either way 3× captures total
  system variance — confirm enrichment determinism during calibration and note it in the writeup.
```
