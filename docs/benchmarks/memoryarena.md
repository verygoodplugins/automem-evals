# MemoryArena preview — AutoMem protocol smoke

Tracking: [#43](https://github.com/verygoodplugins/automem-evals/issues/43).
This is exploratory integration plumbing, not an official benchmark result,
leaderboard submission, or a score claim. The benchmark boundary remains
[documented here](../REPO_BOUNDARY.md).

[MemoryArena](https://memoryarena.github.io/) (ICML 2026,
[arXiv:2602.16313](https://arxiv.org/abs/2602.16313)) evaluates whether an
agent carries experience from one subtask into later dependent subtasks. Its
official [preview repository](https://github.com/ZexueHe/MemoryArena) describes
four surfaces: formal reasoning, group travel planning, progressive web search,
and web shopping. The preview is explicitly actively maintained.

## What is runnable here

[`memoryarena_automem_adapter.py`](../../scripts/benchmarks/memoryarena_automem_adapter.py)
implements the two-method memory-system seam exposed by the upstream preview:

| Preview call | AutoMem operation |
| --- | --- |
| `add_chunk(chunk)` | `POST /memory` with a run/user-scoped tag set |
| `wrap_user_prompt(prompt)` | `GET /recall` constrained to the same tags, then wraps the returned content in `<memory_context>` |

Each `user_id` maps to tags `<run-tag>`, `memoryarena`, and
`user-<user-id>`. The tag gate prevents one benchmark group's trajectory from
leaking into another. The adapter uses only Python's standard library and is
intended to be copied or imported as the `automem` memory-system implementation
in a pinned MemoryArena checkout.

Start a local AutoMem stack, then exercise one dependent-subtask path:

```bash
cd ../automem && docker compose up -d
cd ../automem-evals
python3 scripts/benchmarks/memoryarena_automem_adapter.py \
  --chunk 'Traveler A prefers rail over flights.' \
  --query "Plan traveler B's trip."
```

The command prints a wrapped prompt and always reports:

```text
not_scored: protocol smoke only; no upstream environment, agent, or judge was run
```

That is deliberate. The smoke proves the storage/retrieval contract only and
does not produce a MemoryArena metric.

## Inspected upstream revision and task format

The inspection used the preview revision `6cd9de14b71915e39ac742a20dc33785e14b6aab`
(2026-05-31):

```bash
git clone --depth 1 https://github.com/ZexueHe/MemoryArena.git /tmp/memoryarena-autohub-60e2c548
git -C /tmp/memoryarena-autohub-60e2c548 log -1 --format='%H%n%cs%n%s'
find /tmp/memoryarena-autohub-60e2c548 -maxdepth 3 -type f | sort
sed -n '1,260p' /tmp/memoryarena-autohub-60e2c548/memory/client.py
sed -n '1,260p' /tmp/memoryarena-autohub-60e2c548/memory/server.py
sed -n '1,300p' /tmp/memoryarena-autohub-60e2c548/run_math.py
sed -n '1,360p' /tmp/memoryarena-autohub-60e2c548/setup_formal_reasoning.md
```

The most direct first integration target is formal reasoning. `run_math.py`
loads `ZexueHe/memoryarena` from Hugging Face using a config such as
`formal_reasoning_math` / `test`. Each dataset row has `id`, `paper_name`,
`questions`, `answers`, and `backgrounds`; the runner turns each aligned triple
into a sequential `(subtask, ground_truth, background)` tuple. It writes one
JSONL per paper and the upstream evaluator aggregates per-subtask correctness
into progress and pass-rate-at-k metrics.

## Full-run blockers and exact unblockers

The adapter seam is clear, but a truthful full run is not yet reproducible from
this repository alone. These are the remaining inputs:

| Requirement | Why it blocks a scored run | Unblocker |
| --- | --- | --- |
| Pinned upstream revision plus overlay wiring | The preview `memory/server.py` has a fixed `MEMORY_FACTORIES` map and no `automem` entry. | Add the adapter class to a pinned fork/patch and register `automem`; retain the pinned SHA in the run report. |
| Formal-reasoning environment | The official setup requires `conda env create -f env/env_systems/formal_reasoning_env/environment.yml`, plus an environment server on port 8001 and memory server on port 8000. | Build the documented Conda environment and record its lock/version resolution. |
| Dataset access | Full formal reasoning reads Hugging Face `ZexueHe/memoryarena`, config `formal_reasoning_math` (or `formal_reasoning_phys`), split `test`. | Fetch/cache the dataset and retain its revision plus row count; do not substitute synthetic tasks. |
| Agent and judge model | `agent.base_url`/`agent.model_name` drive task actions; `env.env_config.base_url`/`model_name` drive the per-subtask LLM judge. | Select configured, accessible models and capture model IDs, endpoints (without secrets), temperatures, and judge prompts/config. |
| Other benchmark surfaces | Travel needs the separately downloaded `clean_Flights_2022.csv`; web search needs BrowseComp-Plus decryption, corpus, and FAISS indexes; shopping needs its local runtime plus JDK/spaCy data. | Start with formal reasoning, then provision and validate each environment independently before cross-surface comparison. |

Until those conditions are met, any report must remain `not_scored` and must not
be compared to MemoryArena baselines or a leaderboard.

## Verification

```bash
python3 -m unittest scripts/benchmarks/test_memoryarena_automem_adapter.py
```

The test runs an in-process HTTP protocol double. It verifies that a trajectory
chunk is posted with the expected user isolation tags and that a later prompt
recalls only that scope and receives the upstream `<memory_context>` wrapper.
