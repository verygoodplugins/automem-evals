# BEAM Retrieval-Proxy Harness

This repository owns exploratory AutoMem recall evals. The BEAM runner here is
a deterministic `/recall` harness, not an official BEAM benchmark implementation
and not a claim of end-to-end parity with Graphonomous, Hindsight, mem0, or any
published BEAM leaderboard.

Use `automem` for official benchmark harnesses and published baseline claims.
Use this runner to ask a narrower question:

> When BEAM conversations are loaded into AutoMem, does `/recall` surface
> evidence that matches the source chats and rubric nuggets?

## Harness variants in this repo

There are three BEAM paths here; pick by what you're measuring:

| Runner | Scorer | AutoMem surface | `official_beam_score` |
|---|---|---|---|
| `beam_retrieval_eval.py` (this doc) | deterministic retrieval proxy | native `/recall` | `false` |
| `run_beam.py` | **official** BEAM answer+judge | mem0-impersonating shim | `true` |
| `beam_judged_eval.py` | **official** BEAM answer+judge | **native** `/recall` + PR#12 ingest | `true` |

The retrieval proxy is the cheap, deterministic regression detector. `run_beam.py`
proves AutoMem can pass mem0's wire contract end to end. `beam_judged_eval.py`
(see [§Judged harness](#judged-harness-native-official-scorer)) is the one that
produces a leaderboard-comparable score *through AutoMem's own ingest + recall*,
so server-side ranking changes (e.g. `recency_bias`) can actually move it.

## Commands

Start the local AutoMem stack first:

```bash
cd ../automem
docker compose up -d
```

Then run from this repository:

```bash
# Seed BEAM chunks only.
python3 scripts/beam_ingest.py --tier 100k --sample-conversations 1

# Seed, evaluate, report, then remove seeded BEAM memories.
python3 scripts/beam_eval.py \
  --tier 100k \
  --sample-conversations 1 \
  --question-limit 10 \
  --cleanup-after

# Render a report from a saved result JSON.
python3 scripts/beam_report.py \
  --input data/results/beam-retrieval/<run-id>/results.json

# Remove seeded memories for a saved manifest without rewriting results.
python3 scripts/beam_cleanup.py \
  --manifest data/results/beam-retrieval/<run-id>/manifest.json
```

The lower-level entry point is equivalent:

```bash
python3 runners/beam_retrieval_eval.py ingest --tier 100k
python3 runners/beam_retrieval_eval.py eval --tier 100k
python3 runners/beam_retrieval_eval.py report --input data/results/beam-retrieval/<run-id>/results.json
python3 runners/beam_retrieval_eval.py cleanup --manifest data/results/beam-retrieval/<run-id>/manifest.json
```

## Flags

- `--tier 100k|128k|500k|1m|10m`: `128k` is accepted as a compatibility alias
  for BEAM's `100K` split. There is no `10k` tier.
- `--sample-conversations N`: use the first `N` conversations from the split.
- `--question-limit N`: evaluate the first `N` normalized questions.
- `--manifest PATH`: evaluate an existing ingest manifest instead of seeding.
- `--output DIR`: write run artifacts under this directory. Default:
  `data/results/beam-retrieval/`.
- `--endpoint URL`: AutoMem endpoint. Default: `http://localhost:8001`.
  Non-local endpoints are refused unless `--allow-non-local` is passed.
- `--token TOKEN`: AutoMem API token. Default: `AUTOMEM_API_TOKEN`,
  `LOCAL_AUTOMEM_API_TOKEN`, or `test-token`.
- `--run-id ID`: stable run ID. Tags use `beam-run-<ID>` unless `ID` already
  starts with `beam-run-`.
- `--cleanup-after`: delete every memory recalled under the run tag after the
  command completes.
- `--no-download`: require an existing cached JSON file or `--dataset-json`.
- `--dataset-json PATH`: load BEAM rows from a prepared JSON file.
- `--top-k N`: `/recall` limit per question. Default: `50`.
- `--allow-non-local`: opt in to a non-local endpoint. This should not be used
  for routine repo evals.

## Dataset Loading

The runner first looks for cached JSON in:

```text
third_party/memory-benchmarks/datasets/beam/beam_<tier>.json
```

The vendored upstream BEAM setup often already has `beam_100K.json` there. If
the cache is missing and `--no-download` is not set, the runner attempts the
optional upstream `datasets` package and writes the JSON cache.

Source mapping:

| Tier | Hugging Face dataset | Split |
|---|---|---|
| `100k` / `128k` | `Mohammadta/BEAM` | `100K` |
| `500k` | `Mohammadta/BEAM` | `500K` |
| `1m` | `Mohammadta/BEAM` | `1M` |
| `10m` | `Mohammadta/BEAM-10M` | `10M` |

`probing_questions` is parsed with Python stdlib `ast.literal_eval` first, then
JSON parsing as a fallback. This matches the Hugging Face rows that store Python
literal strings in some exports.

## Ingestion

Each BEAM turn is split into AutoMem memories of at most 500 characters to stay
under AutoMem's soft summarization threshold. Every memory is written through:

```text
POST /memory/batch
```

Tags on every memory:

- `beam`
- `beam-run-<run-id>`
- `beam-tier-<tier>`
- `beam-conv-<conversation-id-slug>`

The runner then creates chronological graph edges between adjacent chunks:

```text
POST /associate
{ "associations": [{ "type": "OCCURRED_BEFORE", ... }] }
```

Association batches are capped at 500 edges per request.
If a local AutoMem build rejects the batch envelope, the runner falls back to
single `POST /associate` calls for compatibility while preserving the same
`OCCURRED_BEFORE` graph shape.

## Scoring

The result JSON is deliberately labeled as:

```json
{
  "runner": "beam-retrieval-proxy",
  "official_beam_score": false
}
```

Per question, the runner records:

- `source_chat_hit`: whether retrieved memory metadata intersects BEAM
  `source_chat_ids`, when those IDs exist.
- `rubric_overlap`: token overlap between BEAM rubric nuggets and retrieved
  memory text.
- `abstention_evidence_absent`: for abstention questions, whether retrieved
  text lacks rubric-level evidence.
- `proxy_score`: deterministic rollup used for local comparison only.

Aggregates include all 10 BEAM ability categories, even when a limited sample
has zero questions for a category.

## Artifacts

Each run writes:

```text
data/results/beam-retrieval/<run-id>/
|-- manifest.json   # run tags, chunk IDs, source chat IDs, normalized questions
|-- results.json    # per-question retrieval metrics + aggregates
`-- report.md       # markdown summary
```

## Cleanup

Use `--cleanup-after` for smoke runs. To remove a run later, rerun against the
same run ID with cleanup enabled:

```bash
python3 scripts/beam_cleanup.py \
  --manifest data/results/beam-retrieval/<run-id>/manifest.json
```

Cleanup recalls by exact `beam-run-<run-id>` tag and deletes the returned memory
IDs. If AutoMem volumes are reset, old manifests remain useful as records but
their memory IDs no longer refer to live server state.

## Judged harness (native, official scorer)

`runners/beam_judged_eval.py` (wrapper: `scripts/beam_judged.py`) runs the **official
BEAM scorer** — the LLM rubric-nugget judge (0/0.5/1.0 per nugget, question score =
mean, pass ≥ 0.5) plus Kendall tau-b for `event_ordering` — over answers generated
from AutoMem's **native** `/recall`. It reuses PR #12 ingest (chunking,
`OCCURRED_BEFORE`) and additionally maps each turn's `time_anchor` to the memory
`timestamp`, so the answer prompt and recall see real per-turn dates.

The answer prompt, judge prompt, and `LLMClient` are imported from the vendored
upstream submodule (`third_party/memory-benchmarks`); the small judge/score
orchestration helpers are ported into the runner so it does not import the
upstream mem0/pydantic dependency chain.

### Requirements

- `OPENAI_API_KEY` (loaded from `REPO/.env` if not exported).
- Upstream deps: `pip install -r third_party/memory-benchmarks/requirements.txt`,
  or use the existing `.venv-beam` (Python ≥ 3.10 — the runner uses `X | None`).
- A local AutoMem stack at `http://localhost:8001`.

### Commands

```bash
# Smoke: one conversation, cheap models (exercises all 10 abilities + tau).
.venv-beam/bin/python scripts/beam_judged.py \
  --sample-conversations 1 --answerer-model gpt-5-mini --judge-model gpt-5-mini

# Headline 100K run, official default models (gpt-5 answerer + gpt-5 judge).
.venv-beam/bin/python scripts/beam_judged.py --tier 100K \
  --answerer-model gpt-5 --judge-model gpt-5

# Ranking sweep (#194): the judged score IS sensitive to these; the proxy is not.
.venv-beam/bin/python scripts/beam_judged.py --recency-bias auto      # temporal rescore
.venv-beam/bin/python scripts/beam_judged.py --min-score 0.4          # relevance gate

# Ablation: ingest WITHOUT the time_anchor->timestamp mapping.
.venv-beam/bin/python scripts/beam_judged.py --no-timestamps
```

### Notable flags

- `--top-k N` / `--cutoffs 100`: recall depth and the answer cutoff(s). `top_100`
  matches the existing `run_beam.py` baseline and the BEAM 100K convention.
- `--recency-bias off|auto|on` and `--min-score FLOAT`: AutoMem `/recall` ranking
  knobs passed straight through, for the #194 sweep.
- `--no-timestamps`: disable the `time_anchor` → `timestamp` mapping (ablation).
- `--sample-conversations N` / `--question-limit-per-conv N`: smoke sizing.
- `--keep`: skip cleanup (leave memories for inspection).

### Scoring + comparability

Result JSON is labeled `official_beam_score: true` with the exact scoring method,
the answerer/judge models, the ranking flags, and `judge_usage` (call counts)
recorded in `metadata`. `metrics_by_cutoff` matches the official shape (per-ability
+ overall accuracy at the 0.5 pass threshold).

The number is a **BEAM 100K-tier** score — comparable to other systems' published
100K numbers (Hindsight 100K = 75%), **not** the 10M leaderboard headline. The
mem0-shim baseline (`run_beam.py`, gpt-5-mini) was 76.25% at this tier; it is
recorded in the artifact metadata for reference.

### Efficiency axes (latency + tokens) — report the triplet, not just accuracy

The public BEAM leaderboard is a **triplet**: accuracy **/ recall latency (ms) /
context tokens**. Accuracy is judge-polluted (±12pts on judge choice); latency and
tokens are **objective and judge-independent**, so they're the cleaner comparison.
Every judged run now records, per question, `retrieval.recall_latency_ms` (timed
around the `/recall` call) and `cutoff_results[*].context_tokens` (real tiktoken
count of the answer prompt), summarized in `metadata.efficiency`
(mean/median/p95 + tokenizer).

Preliminary AutoMem @100K: **~1.6 s recall / ~11k context tokens** vs Hindsight's
published **6.4 s / 17.7k** — i.e. ~4× faster recall and ~35% leaner context. These
are the axes where AutoMem's fast, compact, graph-native recall plausibly *wins*
even where the judge-confounded accuracy number is only competitive. Always report
all three; never quote accuracy alone as a head-to-head.

### Isolation

Each conversation is ingested under `beam-run-<id>`, evaluated, then cleaned up
before the next, with a final sweep. `/health` `memory_count`/`vector_count` are
captured before and after; the runner exits non-zero if `memory_count` does not
return to baseline. (Qdrant may carry pre-existing orphaned vectors, so vector
drift is reported but not a hard gate.)

## Sources

- [BEAM repository](https://github.com/mohammadtavakoli78/BEAM)
- [Mohammadta/BEAM](https://huggingface.co/datasets/Mohammadta/BEAM)
- [Mohammadta/BEAM-10M](https://huggingface.co/datasets/Mohammadta/BEAM-10M)
- [OpenReview ICLR 2026 page](https://openreview.net/forum?id=y59hf5lrMn)
- [Graphonomous BEAM page](https://graphonomous.com/benchmarks/beam)
