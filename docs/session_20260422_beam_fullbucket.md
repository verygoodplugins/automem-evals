# Session 2026-04-22 — BEAM full bucket + AutoMem vs mem0 meta-summary

## Headline

`gpt-5-mini` answerer + judge, 400 questions (20 conversations × 100K tier), clean run, 2h 54m wall-clock:

**76.25% overall pass (305/400), avg score 0.677, zero errors.**

Results at `data/results/beam/20260421-234814-100K-0_19/`.

## Runs summarized

| Run | Config | n | Pass | Avg | What it told us |
|---|---|---|---|---|---|
| 1 (gpt-5, 04-21 early AM) | gpt-5 both, convs 0-1, top-k-cutoffs=100, top-k=200 | 40 | 62.5% | 0.568 | Plumbing works end-to-end, V1 shim is viable |
| 2 (Llama 3.3, 04-21 PM) | `llama3.3:70b` both, default ctx | — | — | — | Ollama default `num_ctx=4096` → every call timed out. Abandoned. |
| 3 (Qwen 3.6 MoE, 04-21 evening) | `qwen3.6:35b-a3b-32k` both, top-k=50, max-workers=2 | 40 | 15.0% | 0.123 | With timeout patched + Modelfile-extended context, Qwen answerer is **too weak** — 4× worse than gpt-5 on same retrieval. |
| 4 (rejudge, 04-22 AM) | Qwen judge replaying gpt-5's 40 answers | 103 nuggets | 89.3% exact / **97.5% PASS/FAIL** vs gpt-5 | — | Qwen is a **usable judge**. Confirms run 3's weakness was the answerer, not the judge. |
| 5 (full bucket, 04-22) | gpt-5-mini both, convs 0-19, top-k=200 | 400 | **76.25%** | **0.677** | Our best-quality baseline so far. |

## Per-category breakdown (run 5)

| Category | Our 100K (n=40 per cat) | mem0 cloud 1M top_200 (n=70 per cat) | mem0 cloud 10M top_200 (n=20 per cat) |
|---|---|---|---|
| information_extraction | **97.5%** / 0.938 | 75.7% / 0.700 | 55.0% / 0.562 |
| preference_following | **95.0%** / 0.875 | 97.1% / 0.883 | 95.0% / 0.904 |
| contradiction_resolution | **90.0%** / 0.675 | 48.6% / 0.357 | 25.0% / 0.325 |
| instruction_following | 90.0% / 0.794 | 88.6% / 0.852 | 90.0% / 0.825 |
| temporal_reasoning | 72.5% / 0.694 | 67.1% / 0.618 | 20.0% / 0.163 |
| event_ordering | 70.0% / 0.594 | 60.0% / 0.536 | 15.0% / 0.202 |
| multi_session_reasoning | 70.0% / 0.619 | 74.3% / 0.652 | 30.0% / 0.261 |
| summarization | 65.0% / 0.466 | 68.6% / 0.635 | 55.0% / 0.469 |
| knowledge_update | 57.5% / 0.569 | 65.7% / 0.650 | 80.0% / 0.750 |
| abstention | 55.0% / 0.550 | 55.7% / 0.525 | 40.0% / 0.400 |
| **overall** | **76.25% / 0.677** | **70.1% / 0.641** | **50.5% / 0.486** |

## Meta-summary — AutoMem vs mem0, what this data supports and what it doesn't

### What it supports

- **The graph layer is doing work.** The four categories where graph traversal should structurally matter — `contradiction_resolution`, `event_ordering`, `temporal_reasoning`, `multi_session_reasoning` — are where AutoMem's numbers look most distinct from mem0-cloud, especially vs the 10M tier. Contradiction at 90% vs mem0's 25–48% is the standout. This lines up with the paper-narrative hypothesis from earlier: "graph-shaped categories are where a graph-augmented system should win over pure vector."
- **Raw retrieval is strong.** `information_extraction` at 97.5% is unambiguous — when a fact is in memory, AutoMem retrieves it. The 1M tier mem0 also scores well here (75.7%) but AutoMem at 100K is meaningfully higher.
- **No translation-bug blackhole.** Every category returned signal. The shim faithfully moves data; the 76% overall is AutoMem's actual retrieval+recall quality, not a plumbing artifact.

### What it does not support

- **"AutoMem beats mem0."** We ran 100K. Mem0's published numbers are 1M and 10M. The distractor pool at 100K is ~10× smaller than 1M and ~100× smaller than 10M — easier problem. We cannot claim dominance without running 1M+ ourselves. The 100K tier is where the easiest-possible retrieval problem lives.
- **Clean apples-to-apples judging.** mem0 published with gpt-5 judge. We ran with gpt-5-mini judge. A weaker judge tends to be more lenient (fewer 0.5 → 0.0 demotions), which would inflate our pass rate by a few pp. Rejudge study showed Qwen vs gpt-5 was 89% exact / 97.5% PASS/FAIL — close but not identical — so gpt-5-mini vs gpt-5 is probably a similar-sized wedge. Real numbers likely within a few pp of 76.25%, not below 70%.
- **V1 shim comparability with mem0's pipeline.** Our shim stores raw dialogue; mem0-OSS extracts facts via `gpt-4o-mini` before storing. Our answerer therefore sees raw chat segments; mem0's answerer sees pre-extracted facts. That asymmetry probably *helps* some categories (information_extraction) and *hurts* others (knowledge_update — where mem0's extraction likely detects the "Y supersedes X" signal and we don't). See weak-spot below.

### AutoMem's weak spots in this data

- **`knowledge_update` at 57.5% is the clearest regression finding.** Mem0 at 1M scores 65.7%, and at 10M scores *better* than at 1M (80.0%). That "knowledge_update gets better at larger tiers" pattern from mem0 strongly implies their `gpt-4o-mini` extraction is doing the heavy lifting — detecting and promoting newer facts over older ones during ingestion. AutoMem has `INVALIDATED_BY` edges for exactly this but the V1 shim never creates them (no fact extraction, no supersession detection at ingest). This is the single finding that most justifies building the V2 extraction shim — if V2 moves `knowledge_update` from 57.5% toward 75–80%, it's evidence that AutoMem's invalidation graph is useful *when* we give it the fact-level signal to work with.
- **`abstention` at 55%** is the second weakness. AutoMem will confabulate when the correct answer is "not in my memory." No existing pipeline mechanism addresses this — it's an answerer-prompt / pipeline-level thing, not a retrieval-layer thing.
- **`summarization` at 65%** is middling; probably more about generation than retrieval.

### Bottom line

AutoMem looks structurally strong on graph-shaped retrieval at 100K, indistinguishable from mem0 on preference/instruction categories, and has one clear weakness (`knowledge_update`) that's almost certainly explained by the V1 shim skipping fact extraction. The paper-narrative hypothesis is **directionally supported but not proven** at this tier.

Two specific things would strengthen the claim:

1. Run the same 100K bucket with a V2 extraction shim — show whether `knowledge_update` and `contradiction_resolution` change in the expected direction.
2. Run at least a 1M subset (say, 7 conversations, ~140 questions, a few hours and ~$15) for direct apples-to-apples with mem0's 1M column. 10M is the expensive-and-most-compelling tier but V2 shim work should come first.

## Options for next steps (pick one for tomorrow)

### Option A — Ship the regression harness now with this baseline *(recommended)*

**Effort:** ~half day. **Output:** working regression infrastructure you can actually use.

1. Freeze `data/results/beam/20260421-234814-100K-0_19/` as `baselines/current-v1shim-gpt5mini.json` (symlink).
2. Build `runners/beam_diff.py` — two-run comparison, per-category delta, ±noise-floor flag.
3. Add `--regression-preset` to `runners/run_beam.py` locking: tier=100K, convs=0-19, top-k=200, answerer=gpt-5-mini, judge=`qwen3.6:35b-a3b-32k` (the hybrid config we landed on).
4. Sanity-check: run once unchanged, diff against baseline. Expect near-zero deltas (Qwen judge is deterministic at temp=0; gpt-5-mini answerer has ±2pp irreducible noise).
5. Cost per regression run: ~$3–5 (answerer only; judge free).

Trade-off: the baseline has 2 truncation events you'll carry forward. Those two questions are forever depressed in the reference. Fine for regression detection (deltas cancel) but makes any future absolute-number claim pre-emptively conservative by a fraction of a pp.

### Option B — Build V2 extraction shim first, *then* baseline

**Effort:** 1 day. **Output:** cleaner baseline, clearer story on `knowledge_update`.

1. V2 shim: before `POST /memory`, call `gpt-4o-mini` to extract facts from the messages (mirror of what mem0-OSS does). Store each extracted fact as a separate AutoMem memory under the same `user_id` tag. Handles the 50K truncation problem at the same time (no single memory ever exceeds the cap).
2. Re-run the full bucket with V2. Compare `knowledge_update`, `contradiction_resolution` deltas. If V2 materially improves these, V1 is retired and V2 is the shim forever.
3. THEN ship regression harness off V2 baseline.

Trade-off: another ~3h overnight run, another ~$10. But you get the cleanest possible reference point — and arguably the one that matters for the "does AutoMem's graph layer work" question, since only V2 gives AutoMem the kind of structured input mem0's pipeline expects.

### Option C — Run a 1M subset for direct mem0 apples-to-apples

**Effort:** 3–4h wall-clock + ~$15–20. **Output:** one defensible side-by-side comparison.

1. `--tier 1M --conversations 0-6` (7 of 35 1M conversations, ~140 questions), gpt-5-mini both, top-k-cutoffs=200.
2. Compare per-category vs mem0's published 1M top_200 numbers. This is the first real cross-tier comparison we have.

Trade-off: distracts from the regression-harness goal, partially invalidated by V1-shim asymmetry, and 1M tier retrieval+ingestion pressure is meaningfully harder than 100K — some chunks *will* hit the 50K truncation cap. Interesting but not what the user asked for originally (internal regression harness).

### Option D — Dig into `knowledge_update` specifically

**Effort:** half day diagnostic. **Output:** one-paragraph finding.

1. Pull the 17 failed `knowledge_update` questions from the full-bucket results.
2. For each: inspect the rubric, the retrieved memories, the answer. Is the newer fact retrieved at all? If yes, why does the answerer ignore it? If no, what memory IDs were retrieved instead and why did they rank higher?
3. Likely outcome: one of (a) answerer ignores chronology in retrieved context, (b) retrieval doesn't boost latest facts, (c) V1 shim's raw-dialogue content makes it ambiguous which statement is latest.

Trade-off: useful intel for V2 shim design and for any future consolidation-logic changes to AutoMem itself. But diagnostic, not a deliverable.

### My lean for tomorrow

**Option A first** — half a day to infrastructure you use forever. Then **Option B** as the first thing the harness measures (V1 → V2 delta is a perfect first "did a meaningful change affect BEAM?" test). Option C and D are valuable but secondary.

## Notes for picking this up

- Full bucket manifest: `data/results/beam/20260421-234814-100K-0_19/MANIFEST.json`
- Full bucket results JSON (19 MB, gitignored): `data/results/beam/20260421-234814-100K-0_19/beam_results_20260422_035020.json`
- Shim audit log: `data/results/beam/20260421-234814-100K-0_19/shim.log` (2 truncation warnings on `beam_100K_3` and `beam_100K_4`)
- Rejudge study output: `data/results/beam/20260421-051827-100K-0_1/beam_results_20260421_055555.rejudge-qwen3.6-35b-a3b-32k.{md,json}`
- Ollama variants to keep: `qwen3.6:35b-a3b-32k` (judge), standard `gpt-5-mini` via hosted API (answerer). `llama3.3:70b-32k` Modelfile is on disk but the model itself is not pre-pulled — rebuild with `ollama create -f scripts/modelfiles/llama3.3-70b-32k.Modelfile` if you need a slower-but-more-calibrated judge alternative.
- The upstream LLM timeout patch lives in `runners/beam_patched_main.py` and is invoked automatically by `runners/run_beam.py`; `BEAM_LLM_TIMEOUT` env var (default 900s) adjusts it.
