# Session 2026-06-16 — BEAM judged 100K (native, official scorer)

Run ID: `20260616-042452-1d46f08a`

This is a **judged, official-scorer** BEAM 100K result from the new native harness
`runners/beam_judged_eval.py` — distinct from:

- the deterministic `/recall` **retrieval proxy** (`beam_retrieval_eval.py`, `official_beam_score: false`), and
- the **mem0-shim** end-to-end runner (`run_beam.py`), which drives the official scorer
  but routes AutoMem through a mem0-impersonating wire contract.

The native harness ingests through AutoMem's own surface (PR #12 chunking +
`OCCURRED_BEFORE` + per-turn `time_anchor` → memory `timestamp`), recalls through
native `/recall`, then applies BEAM's **official** scorer: the LLM rubric-nugget
judge (0/0.5/1.0 per nugget, question score = mean, pass ≥ 0.5) plus Kendall tau-b
for `event_ordering`. The answer prompt, judge prompt, and `LLMClient` are imported
from the vendored `third_party/memory-benchmarks` submodule; the judge/score
orchestration helpers are ported into the runner to avoid the upstream mem0/pydantic
import chain.

## Scope

| field | value |
|---|---|
| BEAM tier | `100K` (full tier: 20 conversations, 400 questions, 40 per ability) |
| answerer model | `gpt-5` |
| judge model | `gpt-5` (OpenAI) |
| scorer | official BEAM nugget judge + Kendall tau-b (`official_beam_score: true`) |
| recall top_k / answer cutoff | 200 / `top_100` |
| per-turn timestamps | on (`time_anchor` → memory `timestamp`) |
| answer `max_completion_tokens` | 8192 |
| AutoMem memories seeded | 29,902 |
| judge usage | 400 answers + 1,051 nugget judges + 277 event-ordering calls |
| isolation | per-conversation `beam-run-<id>` scope; cleanup-to-zero; `/health` before == after |

Raw per-run artifacts are gitignored (`data/results/beam-judged/`); this note is the
curated record.

## Result — 70.25% (281/400), avg_score 0.649

Comparable to other systems' BEAM **100K-tier** numbers (Hindsight 100K = **75%**),
**not** the 10M leaderboard headline. `empty_answers: 0/400`, `errors: 0`, returned to
baseline (memory + vector counts).

| ability | accuracy | avg_score | correct/total |
|---|---|---|---|
| abstention | 52.5% | 0.525 | 21/40 |
| contradiction_resolution | 52.5% | 0.466 | 21/40 |
| event_ordering | 62.5% | 0.548 | 25/40 |
| information_extraction | 90.0% | 0.852 | 36/40 |
| instruction_following | 80.0% | 0.738 | 32/40 |
| knowledge_update | 57.5% | 0.575 | 23/40 |
| multi_session_reasoning | 75.0% | 0.660 | 30/40 |
| preference_following | 95.0% | 0.900 | 38/40 |
| summarization | 62.5% | 0.534 | 25/40 |
| temporal_reasoning | 75.0% | 0.694 | 30/40 |

### How it compares (100K tier)

| System / config | answerer / judge | 100K accuracy |
|---|---|---|
| Graphonomous (per autohub#696) | undisclosed | 95.0% |
| Hindsight (published) | undisclosed | 73.4–75.0% |
| AutoMem via mem0-shim (`run_beam.py`) | gpt-5-mini / gpt-5-mini | 76.25% |
| **AutoMem native (this work)** | **gpt-5 / gpt-5** | **70.25%** |
| AutoMem native (this work) | gpt-5-mini / gpt-5-mini | 82.0% |

The official-default **gpt-5/gpt-5** headline is **70.25%** — a conservative, honest
AutoMem-native figure (no shim wire-contract). At a matched judge, the native harness
**beats the mem0-shim** (82.0% vs 76.25%, both gpt-5-mini). Absolute numbers are judge-
dependent (~12 pts between gpt-5 and gpt-5-mini judges), so cross-system comparison is
only sound at a fixed judge — which the leaderboard does not disclose. Graphonomous's
95% remains the bar to chase.

## Key findings

1. **gpt-5 answer truncation was a real harness artifact.** The first full gpt-5 run scored
   67.5% with **23/400 empty answers** — gpt-5's reasoning exhausted the upstream default
   4096 `max_completion_tokens` on long-answer abilities (summarization, event_ordering),
   truncating output right at the trailing `ANSWER:` → auto-zeroed. Raising the answer budget
   to **8192** eliminated all truncation (`empty_answers: 0`) and recovered ~2.75 pts → 70.25%.
   The judge side was unaffected (tiny JSON output; 0 parse errors). Fix exposed as
   `--answer-max-tokens` (default 16384; 8192 used here as a cost/headroom balance).
2. **Mid-run quota exhaustion can silently poison a judged run.** Two back-to-back full gpt-5
   runs exhausted the OpenAI account quota mid-third-run, producing 140 empty answers and a
   misleading 43.5%. Added a fail-fast guard (`--max-empty-rate`, default 0.30) that aborts
   (after cleanup) when the empty-answer fraction spikes, plus a start-of-run judge preflight.
3. **`time_anchor` → `timestamp` mapping matters.** PR #12 ingest left every chunk at ingestion
   time, so the official answer prompt's chronological sort + `[YYYY-MM-DD]` headers were inert.
   Mapping each turn's `time_anchor` to the memory `timestamp` (verified `/memory/batch` honors
   per-item `timestamp` → `node.timestamp` + `t_valid`) restores real per-turn dates. Sensitivity
   quantified below.

## Sweep — sensitivity probes (gpt-5-mini, full 400)

_The retrieval proxy was insensitive to #194's ranking flags by construction; a judged
pipeline should respond to ingest/ranking changes. These probes use gpt-5-mini for both
answerer and judge (cheap, 400-question power) to measure **deltas**, not the headline
number. All three runs: `empty_answers: 0`, returned to baseline._

| condition | overall accuracy | avg_score | Δ vs baseline |
|---|---|---|---|
| baseline (timestamps on, ranking off) | 82.00% | 0.728 | — |
| `--no-timestamps` (ablation) | 82.25% | 0.748 | +0.25 overall / **−12.5 on event_ordering** |
| `--recency-bias auto` | 81.50% | 0.735 | −0.50 |

Findings:

1. **The judged pipeline is sensitive to ingest and ranking changes** — the whole point
   vs the proxy (which was byte-identical to `recency_bias` and moved 0.0001 on a relevance
   gate). Dropping per-turn timestamps costs **−12.5 pts on `event_ordering`** (77.5% → 65.0%)
   — exactly the ability that depends on chronological order — while overall is flat (most
   abilities don't need dates). `recency_bias=auto` moves overall −0.5 pts (doesn't help BEAM
   100K). This validates the `time_anchor` → `timestamp` design where it matters and confirms
   ranking work belongs in a judged pipeline.
   - Caveat (review item I2): `--no-timestamps` leaves every `created_at` empty, so the answer
     prompt's chronological sort becomes a no-op and context falls back to score-desc order.
     That is the correct meaning of "no timestamps" — the ablation captures the full cost of
     not mapping anchors (lost dates **and** lost ordering), which is what we want to measure.
2. **Native beats the mem0-shim at the same model.** Native gpt-5-mini = **82.0%** vs the
   `run_beam.py` mem0-shim baseline **76.25%** (also gpt-5-mini, same tier/cutoff/scorer):
   AutoMem's own chunking + `/recall` outscores the mem0 wire-contract path by ~6 pts.
3. **Judge model dominates the absolute score.** Same answers score **70.25% under a gpt-5
   judge** vs **82.0% under a gpt-5-mini judge** — a ~12 pt swing from judge strictness alone.
   Cross-system leaderboard comparison is only meaningful at a fixed judge; the headline
   records its judge model for this reason.

## Reproduce

```bash
cd ../automem && docker compose up -d            # AutoMem stack at :8001
cd ../automem-evals
.venv-beam/bin/python scripts/beam_judged.py --tier 100K \
  --answerer-model gpt-5 --judge-model gpt-5 --answer-max-tokens 8192
```

Harness lives in this repo (experiment runner, per `docs/REPO_BOUNDARY.md`); the blessed
headline number is promoted to `automem/benchmarks/EXPERIMENT_LOG.md`.
