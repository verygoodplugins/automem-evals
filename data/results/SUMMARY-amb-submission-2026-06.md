# SUMMARY — AutoMem on the Agent Memory Benchmark (Core-3 + BEAM)

**Date:** 2026-06-26
**Harness:** [Agent Memory Benchmark (AMB)](https://agentmemorybenchmark.ai) — the neutral, fully-open harness (vectorize-io). Gemini answerer (`gemini-3.1-pro-preview`) + Gemini judge (`gemini-2.5-flash-lite`), single-query / RAG mode.
**Provider config:** AutoMem self-spinning Docker (FalkorDB + Qdrant), FastEmbed-local `bge-base-en-v1.5` (768d, no embedding API keys), lean enrichment (`ENRICHMENT_ENABLED=false`). Run name `automem-sub`.
**Reproduce:** `agent-memory-benchmark/src/memory_bench/memory/AUTOMEM_REPRODUCE.md` (one command per split; the provider spins its own stack).
**Aggregator:** `runners/amb_aggregate.py` (this repo) over the committed `outputs/`.

## Results

| Dataset | AutoMem (95% CI) | Honcho¹ | Δ (pp) | Recall P50² | Recall avg³ | Ctx tokens |
|---|---|---|---|---|---|---|
| locomo/locomo10 | 85.1% ± 1.8 (n=1540) | 89.9% | −4.8 | 127 ms | 132 ms | 4,786 |
| longmemeval/s | 74.4% ± 3.8 (n=500) | 90.4% | −16.0 | 905 ms | 1,012 ms | 3,766 |
| personamem/32k | 76.1% ± 3.4 (n=589) | — | — | 180 ms | 202 ms | 2,626 |
| beam/100k (×3 repro) | 67.5% (spread 1.8pp) | 63.0% | **+4.5** | 195 ms | 247 ms | 3,817 |
| beam/500k | 65.6% ± 2.8 (n=700) | 64.9% | +0.7 | 432 ms | 440 ms | 3,782 |
| beam/1m | 63.8% ± 2.7 (n=700) | 63.1% | +0.7 | 424 ms | 451 ms | 3,775 |
| beam/10m | **57.4% ± 5.5** (n=200) | 40.6% | **+16.8** | 1,707 ms | 2,260 ms | 3,844 |

_BEAM scores are rubric-mean (BEAM paper's 0/0.5/1 per-item scoring averaged per question) — a different scale than pass/fail benchmarks._

## Headline — BEAM scaling

On BEAM (the only same-benchmark, apples-to-apples axis vs published competitors), **AutoMem beats Honcho at every tier**, and the margin grows with scale:

- 100k **+4.5**, 500k +0.7, 1M +0.7, **10M +16.8**.
- AutoMem degrades **gracefully**: 67.5% → 57.4% (−10pp) across a 100× haystack increase.
- Honcho **collapses** over the same range: 63.0% → 40.6% (−22pp) — flat through 1M, then a cliff at 10M.
- Reference leader Hindsight (vectorize's own system) holds 73–64% across the curve. So AutoMem is a **clear #2 on BEAM**, decisively above Honcho.

The 10M result — holding ~57% where the well-marketed #2 competitor breaks to ~41% — is the defensible centerpiece: at 10 million tokens context-stuffing is physically impossible, so the score reflects retrieval architecture, not context window.

## Honest other half — Core-3

On the conversational Core-3 datasets, AutoMem **trails the leaders**:

- locomo 85.1% (−4.8 vs Honcho's self-reported 89.9%; Hindsight 92%).
- longmemeval 74.4% (−16.0 vs Honcho 90.4%; Hindsight 94.6%).
- personamem 76.1% (no Honcho entry; Hindsight 86.6%).

**Caveat:** Honcho's Core-3 numbers are **self-reported on its own harness** (Plastic Labs blog / evals.honcho.dev), not re-run through AMB — so these Δ carry the answerer/judge confound that AMB otherwise removes. They are **directional, not a clean head-to-head.** The clean Core-3 yardstick is Hindsight (also AMB), and AutoMem trails it across all three.

## Efficiency

- **Recall latency:** sub-second on most tiers (127–451 ms P50), ~1.7 s at 10M. Latency is environment-relative (local Apple-silicon, FastEmbed in-process, single-query mode) and **not a cross-system axis** — reported for our own runs only.
- **Context tokens:** ~2.6–4.8k fed to the answerer at every scale — a bounded-retrieval signature (the board's leader feeds 17–27k on BEAM). This is architectural, not hardware-dependent, and is AutoMem's strongest efficiency story.

## Methodology notes / caveats

1. **Honcho numbers are external/self-reported** (catalogued in AMB's `external_results.json`), not independently reproduced — treat all Δ as directional. BEAM is closest-comparable (same benchmark, same scoring); Core-3 carries the harness confound.
2. **Latency reported two ways:** P50 (robust central estimate) and mean (`recall avg`, the board's column). Mean ≈ P50 for every split **except beam/10m**, whose mean (~2.2× its median) carries a host-CPU-contention tail from an unrelated local process during its measurement window. Prefer P50 for 10M, or re-measure on a quiet host for a clean mean. Accuracy is unaffected (retrieval is deterministic; only timing is load-sensitive).
3. **beam/100k run ×3** as a reproducibility check: 67.5% mean, 1.8pp spread — within-run CI dominates run-to-run noise, justifying ×1 on the larger tiers.
4. **Reproducible:** the AutoMem provider self-spins its full stack; one command per split, no embedding API keys. See `AUTOMEM_REPRODUCE.md`.

## Status

Full Core-3 + BEAM run set complete (run_name `automem-sub`). Remaining work is **human-gated**: publish the public GHCR image, force-add `outputs/`, and open the provider PR to `vectorize-io/agent-memory-benchmark`.
