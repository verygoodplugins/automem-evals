# BEAM Retrieval-Proxy Harness

This repository owns exploratory AutoMem recall evals. The BEAM runner here is
a deterministic `/recall` harness, not an official BEAM benchmark implementation
and not a claim of end-to-end parity with Graphonomous, Hindsight, mem0, or any
published BEAM leaderboard.

Use `automem` for official benchmark harnesses and published baseline claims.
Use this runner to ask a narrower question:

> When BEAM conversations are loaded into AutoMem, does `/recall` surface
> evidence that matches the source chats and rubric nuggets?

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

## Sources

- [BEAM repository](https://github.com/mohammadtavakoli78/BEAM)
- [Mohammadta/BEAM](https://huggingface.co/datasets/Mohammadta/BEAM)
- [Mohammadta/BEAM-10M](https://huggingface.co/datasets/Mohammadta/BEAM-10M)
- [OpenReview ICLR 2026 page](https://openreview.net/forum?id=y59hf5lrMn)
- [Graphonomous BEAM page](https://graphonomous.com/benchmarks/beam)
