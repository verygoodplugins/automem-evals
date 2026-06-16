# Memory Maturation — benchmark methodology (cold vs matured)

## The problem

AutoMem is a *living* memory system: enrichment, consolidation, and decay run as
background maintenance on a **wall-clock schedule** (decay daily, creative weekly,
clustering monthly — see `automem/config.py:CONSOLIDATION_*`). A benchmark, by
contrast, ingests a months-long conversation in **seconds**, queries immediately,
then deletes. So none of that machinery fires: the enrichment queue lags thousands
deep, consolidation never runs, decay never triggers. **BEAM/LoCoMo/LongMemEval, as
normally run, test AutoMem's cold retrieval substrate — not its cognitive layer.**

This was confirmed on the BEAM 100K run: 94% retrieval recall, only 9/400 failures
are recall-misses, and the one genuinely AutoMem-actionable miss (a `knowledge_update`
stale value) is exactly an `INVALIDATED_BY`/consolidation case that the cold ingest
never exercises. The score is a **floor**, not a ceiling.

## Standing rule

> **Every benchmark run reports BOTH a `cold` and a `matured` number, and always
> compares them.** Cold is the leaderboard-comparable figure; matured is the
> realistic-deployment story; the delta quantifies AutoMem's cognitive layer.

We can run `cold` alone for a quick check, but a published/curated result always
carries both, produced by a **frozen, versioned maturation profile** applied
**identically across all benchmarks** (BEAM, LoCoMo, LongMemEval).

## Two clocks

| Clock | What it is | Used for |
|---|---|---|
| **Narrative** | the data's `time_anchor` / memory `timestamp` (months span) | decay age, consolidation, recall windowing |
| **Wall-clock** | when we actually ingested (seconds, tonight) | nothing scientific — only "did the queue drain" |

Maturation runs on the **narrative** clock. We don't wait months; we invoke the
same passes AutoMem would run, with `reference_time` set to the question's narrative
"as-of" date. Same code, same formulas, driven by the data's timeline.

## Pipeline & variants

```
ingest (narrative timestamps)
  → [matured] drain enrichment to queue_depth 0
  → [matured] run consolidation passes (decay, cluster, creative, invalidation)
              with reference_time = question's as-of date, to convergence
  → recall (windowed to timestamp <= as-of)        # leakage guard
  → answer → judge
```

| Variant | Maintenance applied | Reported as |
|---|---|---|
| `cold` | none (today's default) | the **leaderboard comparator** |
| `matured` | enrichment + consolidation + clustering + invalidation, **decay/forget OFF** | realistic "warm memory" — usually ≥ cold |
| `matured-full` | the above **+ decay/forget ON** | most realistic; **may score < cold** (see below) |

## Scientific controls (non-negotiable)

1. **Leakage guard.** Answering "as of" date T must only see memories with
   `timestamp <= T`. Decay/consolidation and `/recall` both honor T. No peeking at
   the future to consolidate the past.
2. **Determinism.** Consolidation passes that use embeddings/LLMs must pin models +
   seeds and run to a fixed point (or fixed N). A maturation you can't reproduce is
   not a result.
3. **No per-benchmark tuning.** The profile is set once by a deployment-realistic
   config and frozen. Tuning it per benchmark to maximize a score is overfitting.
4. **Versioned + disclosed.** Every result records `maturation: <profile>` and the
   judge model. Change the profile → bump the version → re-run everything.

## The decay caveat (important)

Decay/forget models *forgetting*, but benchmarks reward *total recall of the entire
history*. So `matured-full` can score **below** `cold` — you correctly down-weighted
an old fact the benchmark then asks about. **That is a finding, not a regression**:
it shows benchmarks structurally under-reward forgetting. Report the delta and
explain it; never bury it, never swap `matured` in as "the score."

## What others do

- **mem0 / Zep (Graphiti) / Letta** do consolidation **synchronously at ingest**
  (LLM fact-extract + dedup/update; bi-temporal edge invalidation). They have no
  lagging background scheduler to starve. So AutoMem's async, queue-behind cold run
  *under-represents* it vs how those systems are benchmarked — "drain before recall"
  mostly puts us on equal footing.
- **Decay/forgetting: essentially nobody simulates it** in benchmark runs; the
  benchmarks bake temporal reasoning into the *questions* and expect retrieval over
  the un-decayed history. So `cold`/`matured` (no-forget) is the fair comparator;
  `matured-full` is an internal honesty metric.
- **Disclosure norms are loose** — nobody publishes their maturation profile or even
  their judge model (the judge alone is worth ±12pts on BEAM). Publishing ours is a
  transparency edge.

## maturation-v1 (profile — to be frozen on implementation)

| Knob | Value | Source |
|---|---|---|
| enrichment | drain to `queue_depth == 0` before recall | `/health.enrichment` |
| decay | base rate `0.01`, threshold `0.3`, **reference_time = as-of** | `CONSOLIDATION_BASE_DECAY_RATE` / `..._DECAY_IMPORTANCE_THRESHOLD` |
| clustering / creative | one pass each, to convergence | `/consolidate` mode |
| invalidation | on (so latest value wins for `knowledge_update`) | consolidation |
| forget | OFF for `matured`, ON for `matured-full` | `CONSOLIDATION_FORGET_INTERVAL` |
| recall window | `timestamp <= as-of` | recall `end` param |
| recency_bias | `off` (held constant with cold) | recall param |

## Implementation status / dependencies

- `runners/beam_judged_eval.py` gains a `--maturation {cold,matured,matured-full}`
  flag that inserts the drain + `/consolidate` calls between ingest and recall.
- **AutoMem dependency:** `/consolidate` decay currently uses wall-clock `now()`
  (`automem/automem/consolidation/...` → `datetime.now()`). Faithful narrative-clock
  decay needs a `reference_time`/`as_of` parameter on the consolidate path. Tracked
  in the implementation issue.
- Until then, `cold` remains the only fully-wired mode; `matured` is specified here
  so every run is labeled `maturation: cold` explicitly rather than silently.

Refs: `docs/session_20260616_beam_judged_100k.md`, `docs/eval/beam.md`.
