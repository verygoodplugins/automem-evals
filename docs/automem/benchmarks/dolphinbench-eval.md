# DolphinBench evaluation assessment

Status: **not_scored** (protocol adapter and offline smoke coverage only)

Tracking issue: [#45](https://github.com/verygoodplugins/automem-evals/issues/45)
Inspected upstream: [`mem0ai/dolphinbench` at `81cb6f8405b40a9e76089cef650806a80af06ea2`](https://github.com/mem0ai/dolphinbench/tree/81cb6f8405b40a9e76089cef650806a80af06ea2)

## Why it is relevant

[DolphinBench](https://dolphinbench.ai/) measures memory by whether an agent
completes simulated knowledge-work tasks, not by direct-answer QA. It has three
personas (Morgan, Alex, and Riley), about 500k user-message tokens per persona,
and 600 tool-using tasks total. Every task is certified with an oracle-history
pass and a no-history failure. The benchmark requires three reported metrics:
accuracy, total cost across ingestion and testing, and median task latency.

Sources: [project site](https://dolphinbench.ai/), [run/submission guide](https://dolphinbench.ai/run/), [paper](https://arxiv.org/html/2609.24971v2), and [Apache-2.0 harness/dataset](https://github.com/mem0ai/dolphinbench).

## Submission protocol verified

The participant harness owns the agent loop, model calls, and memory lifecycle.
The benchmark supplies chronologically ordered histories, test requests, local
simulated MCP applications, action graders, and ZIP packaging. An integration
implements five methods: runtime identity, per-interaction agent execution,
memory freeze, checkpoint verification, and phase cost accounting.

For every configuration, ingestion begins with a separate empty store per
persona and processes the whole history in order. The resulting memory is
durably frozen. Each of 200 persona tests runs in a fresh conversation with
isolated app state and read-only access to that completed memory. Facts,
expected answers, and grader material must remain outside the agent context.

A submission ZIP contains only `ingestion.json` and `tests.json`, but those
files must include the complete all-persona history/test records, actual
per-response API usage, durations, grading evidence, and phase totals. A
submission cannot use invented or unknown costs: the runner validates recorded
`total_cost_usd` and uses the sum of ingestion plus test cost. Latency is the
median task duration, including tool use.

## AutoMem seam added here

[`scripts/benchmarks/dolphinbench_adapter.py`](../../../scripts/benchmarks/dolphinbench_adapter.py)
provides a stdlib-only HTTP backend that maps an agent's normal:

- `store_memory` call during ingestion to `POST /memory`;
- `recall_memory` call to `GET /recall`.

Every request carries three hard-gating tags: `dolphinbench`, a unique
configuration `scope_tag`, and `dolphinbench-persona-<persona>`. This prevents
cross-persona and concurrent-run retrieval leakage. The backend carries the
source narrative timestamp/message ID in metadata and locally closes writes on
`freeze`; a real participant loop must additionally omit `store_memory` from
test-time tools.

This is a backend seam, not a full participant agent: a production run still
needs an agent loop that selects app and memory tools, records every model
response/tool result, persists an AutoMem checkpoint, and reports model plus
memory-processing costs without double counting.

## Result boundary

No accuracy, cost, or latency is claimed. The official non-offline runner
requires `--confirm-paid-calls` for ingestion and evaluation; semantic checks
use Azure `gpt-5.6-sol` at medium reasoning and require
`AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY`. No paid agent/judge run was
configured for this exploratory integration. The offline smoke emits
`not_scored` with all three metrics set to `null`, rather than fabricating a
number.

Run the safe checks:

```bash
python3 -m unittest scripts/benchmarks/test_dolphinbench_adapter.py
python3 scripts/benchmarks/run_dolphinbench_smoke.py
```

When paid credentials and a production agent loop are available, use a new
upstream run directory and follow its `prepare`, `ingest --confirm-paid-calls`,
and `evaluate --confirm-paid-calls` stages. Start with a single persona only as
an internal smoke; do not package or publish it as a valid DolphinBench
submission, which requires all three personas and 600 tests.
