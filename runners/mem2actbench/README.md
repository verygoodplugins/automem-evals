# Mem2ActBench evidence-retrieval runner

Runs AutoMem against [Mem2ActBench](https://arxiv.org/abs/2601.19935), a
memory-to-action benchmark: can an agent recall the prior preference or task
state that grounds a tool call's parameters? This runner scores the **retrieval
half** only. It never generates a tool call.

Dependency-free Node (tested on 24). No `package.json`, no install step.

Results: [`data/results/SUMMARY-mem2actbench-pilot-2026-09-18.md`](../../data/results/SUMMARY-mem2actbench-pilot-2026-09-18.md).
Headline: **77.81% evidence F1, 75.67% labelled-parameter accuracy** over all
400 full-split tasks at k=5, with L4 conflict resolution as the weak spot
(48.72% F1). That is a retrieval-evidence score and is **not comparable** to
the paper's end-to-end 53.8 oracle F1. Tracking: #24.

## What it does

For each QA task:

1. Stores the task's labelled `evolution_chain` facts as `Context` memories
   tagged with a unique run tag, `mem2actbench` and `qa-<qa_id>`.
2. Links consecutive facts with `RELATES_TO` (`POST /associate`).
3. Recalls `--recall-k` facts for the task query, scoped to the run tag
   (`GET /recall`).
4. Scores the recalled text (below), then deletes that task's facts unless
   `--keep` is set.

### Metric contract

A labelled, non-default tool parameter is **supported** when a recalled memory
contains that parameter's labelled source text or the matching chain fact. A
recalled memory that supports no labelled parameter is **false-positive
evidence**. Tool defaults and arguments with no grounding label are excluded.
The report gives parameter accuracy (supported / expected), evidence
precision, recall, F1 and strict task accuracy (every labelled parameter
supported).

Seeding only the labelled chain is deliberately narrow: it isolates retrieval
from memory writes and from argument synthesis, and it faces far fewer
distractors than the benchmark's full session histories. A paper-comparable
pass needs full-history ingestion plus an argument-synthesis step; the SUMMARY
lists the design.

## Dataset

The authors' repo is the source of record. It is untagged, and its README says
MIT but GitHub does not identify a license file, so pin a commit and do not
commit the data. `data/benchmarks/` is gitignored for that reason.

```bash
git clone https://github.com/Cantaloupe-M/Mem2ActBench.git data/benchmarks/mem2actbench
git -C data/benchmarks/mem2actbench rev-parse HEAD   # record this in your writeup
```

The full split is `Mem2ActBench/qa_dataset.jsonl`; the quick-test split is
`toolmembench_small/qa_dataset.jsonl` (the default).

## Run

The runner writes to and deletes from AutoMem. Point it at a local or
disposable stack, not a memory store you care about.

| Variable | Purpose |
| --- | --- |
| `AUTOMEM_API_URL` | AutoMem base URL, e.g. `http://localhost:8001` for the local stack |
| `AUTOMEM_API_KEY` | AutoMem API token, e.g. `test-token` for the local stack |

`AUTOMEM_ENDPOINT` and `AUTOMEM_API_TOKEN` are accepted as deprecated
fallbacks. Both values are required unless `--dry-run` is set.

```bash
# Dataset-shape check. Reads the JSONL, never calls AutoMem.
node runners/mem2actbench/index.mjs --dry-run --limit 3

# Small-split smoke.
AUTOMEM_API_URL=http://localhost:8001 AUTOMEM_API_KEY=test-token \
node runners/mem2actbench/index.mjs \
  --dataset data/benchmarks/mem2actbench/toolmembench_small/qa_dataset.jsonl \
  --limit 40 --run-id mem2actbench-small-smoke

# Full split. For short command wall-times, run 40-task batches with
# --offset 0, 40, 80, ... --limit 40; each batch writes its own report.
AUTOMEM_API_URL=http://localhost:8001 AUTOMEM_API_KEY=test-token \
node runners/mem2actbench/index.mjs \
  --dataset data/benchmarks/mem2actbench/Mem2ActBench/qa_dataset.jsonl \
  --recall-k 5 --run-id mem2actbench-full
```

Reports land in `data/results/mem2actbench/runs/<run-id>.json` (gitignored),
with per-case `complexity`, `retrieved_evidence`, `association_failures` and
unsupported parameters. The runner does not aggregate across batches or by
complexity. Commit a curated aggregate under `data/results/mem2actbench/` plus a
`SUMMARY-*.md` instead of raw reports.

Use `--keep` only for debugging: it leaves the run-tagged facts in AutoMem.

## Verification

```bash
node --test runners/mem2actbench/harness.test.mjs
```

Unit tests for the pure helpers in `lib.mjs`: the fact payload and its tags,
chain associations, resumable batch selection, and parameter-grounding scoring
with defaults excluded.
