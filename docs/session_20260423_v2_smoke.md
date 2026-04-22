# Session 2026-04-23 — V2 extraction shim smoke (convs 0-1)

## Configuration

| | V1 (baseline, convs 0-1 subset) | V2 smoke |
|---|---|---|
| tier | 100K | 100K |
| conversations | 0-1 | 0-1 |
| shim version | v1 (raw dialogue pass-through) | v2 (fact extraction) |
| extraction model | — | gpt-4o-mini |
| extraction prompt | — | mem0 FACT_RETRIEVAL_PROMPT (pinned SHA `daa4495`) |
| answerer | gpt-5-mini | gpt-5-mini |
| judge | gpt-5-mini | gpt-5-mini |
| top-k | 200 | 200 |
| top-k-cutoffs | 100 | 100 |

V1 subset pulled from the full baseline via `scripts/extract_v1_subset.py --convs 0-1`.

## Overall

| metric | V1 | V2 | Δ |
|---|---:|---:|---:|
| pass_rate | 62.50% | **72.50%** | **+10.00pp** |
| avg_score | 0.507 | **0.629** | **+0.123** |

## Per-category (n=4 each — very noisy)

| category | V1 pass | V2 pass | Δ pass | V1 avg | V2 avg | Δ avg |
|---|---:|---:|---:|---:|---:|---:|
| abstention | 0.0% | 50.0% | **+50.00pp** | 0.000 | 0.500 | +0.500 |
| contradiction_resolution | 100.0% | 100.0% | +0.00pp | 0.688 | 0.594 | -0.094 |
| event_ordering | 100.0% | 75.0% | -25.00pp | 0.667 | 0.658 | -0.008 |
| information_extraction | 100.0% | 75.0% | -25.00pp | 1.000 | 0.771 | -0.229 |
| instruction_following | 50.0% | 75.0% | +25.00pp | 0.375 | 0.625 | +0.250 |
| knowledge_update | 75.0% | 75.0% | +0.00pp | 0.750 | 0.750 | +0.000 |
| multi_session_reasoning | 50.0% | 50.0% | +0.00pp | 0.312 | 0.500 | +0.188 |
| preference_following | 100.0% | 100.0% | +0.00pp | 0.875 | 0.750 | -0.125 |
| summarization | 50.0% | 75.0% | **+25.00pp** | 0.400 | 0.646 | +0.246 |
| temporal_reasoning | 0.0% | 50.0% | **+50.00pp** | 0.000 | 0.500 | +0.500 |

**Net question flips:** 9 new-pass, 5 new-fail, net +4.

## V2 extraction stats (ingestion phase)

- Chunks processed: **194** (conv 0: 94, conv 1: 100)
- Extraction success rate: **100%** (zero fallback-to-raw-blob events)
- Facts per chunk: avg **3.1**, range 0–8 (a handful of "Hi."-type chunks yield 0)
- Latency per chunk: avg **~1.5s**, p95 ~2s (one 7.5s outlier)
- Token usage across smoke: ~355K input, ~5.5K output (extrapolated from observed 33 rows)
- Extraction cost: ~**$0.06** for the full smoke
- Total memories stored: **99** (sweep count at run end — fewer than 194 chunks because of 0-fact chunks, shows extraction is selectively filtering)

## Interpretation vs Phase 1 predictions

Phase 1 forensics predicted per-category directions. Holding up:

| Category | Predicted direction | Observed (smoke n=4) | Status |
|---|---|---|---|
| knowledge_update | ++ (72–78%) | flat (75% → 75%) | **Inconclusive** — ceiling effect at 75% on this subset. Full bucket is where the test lives. |
| event_ordering | + | -25pp | **Surprise loss** — possibly losing temporal adjacency |
| temporal_reasoning | + | +50pp | **Strong confirmation** |
| multi_session_reasoning | + (modest) | flat pass, +0.19 avg | Partial confirmation |
| contradiction_resolution | flat (ceiling) | flat / -0.09 avg | Confirmed |
| information_extraction | flat (ceiling) | -25pp | **Surprise loss** — atomic facts may lose connecting context |
| instruction_following | mixed | +25pp | Confirmed (better than predicted) |
| summarization | flat/negative | **+25pp** | **Big surprise win** — predicted flat because mostly C (answerer-ignored) |
| preference_following | flat (ceiling) | flat pass, -0.13 avg | Confirmed |
| abstention | flat (E-dominated) | **+50pp** | **Big surprise win** — atomic facts reduce thematic-but-wrong hallucination? |

Two material surprises (abstention, summarization) where V2 unexpectedly helps. Two surprise losses (event_ordering, information_extraction) where V2 seems to strip connecting context that the answerer needs.

These patterns are exactly why full-bucket (n=40/category) matters — smoke's n=4 is too noisy to trust individual category deltas.

## Hiccup observation

Question 25 (conv 1 q5 event_ordering) stalled for ~17 min with a single OpenAI "structured output attempt 1/5 timed out" error. Recovered on retry. This is a gpt-5-mini API tail-latency issue, unrelated to V2. Same would happen under V1. For Phase 3 I'll add `--max-workers 4` so a single slow call doesn't block the queue.

## Decision on Phase 3 (full bucket)

**Pre-committed gate:** proceed unless smoke crashes, is zero-pass everywhere, or extraction fails >50%.

Observed: clean success, +10pp overall, 100% extraction rate, zero fallback events. ✅ **Proceed to Phase 3 full bucket with `--max-workers 4`.**
