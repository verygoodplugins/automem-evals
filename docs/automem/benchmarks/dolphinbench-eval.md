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

## Follow-up: implicit recall and cost/latency, checked 2026-10-20

Candidate: `opportunity:automem-graph-rag-research-scout`. Searches across open
and closed issues and PRs for `DolphinBench` and `2609.24971` found the direct
tracking issue #45 and merged [PR #46](https://github.com/verygoodplugins/automem-evals/pull/46).
Continue in #45; its closure records the protocol scaffold, not completion of
the scored evaluation. [Follow-up acceptance comment](https://github.com/verygoodplugins/automem-evals/issues/45#issuecomment-6285270104).
Related threads: [#50](https://github.com/verygoodplugins/automem-evals/issues/50),
[#51](https://github.com/verygoodplugins/automem-evals/issues/51),
[#57](https://github.com/verygoodplugins/automem-evals/issues/57),
[#62](https://github.com/verygoodplugins/automem-evals/issues/62),
[PR #66](https://github.com/verygoodplugins/automem-evals/pull/66), and
[StreamMemBench #67 / PR #68](https://github.com/verygoodplugins/automem-evals/pull/68).
These diagnose different memory behaviors and remain separate experiments.

The [v2 paper](https://arxiv.org/abs/2609.24971v2) motivates **implicit recall**:
the request does not announce that retrieval is needed or identify the fact.
Measure whether AutoMem recall and graph expansion help the agent select and
apply historical context through its actions. Compare configurations on an
accuracy/cost/latency Pareto frontier, keeping each metric separate.

### Pinned artifacts and availability

Dataset and harness both use the inspected upstream commit
`81cb6f8405b40a9e76089cef650806a80af06ea2` (2026-09-23).
The [root license](https://github.com/mem0ai/dolphinbench/blob/81cb6f8405b40a9e76089cef650806a80af06ea2/LICENSE)
is Apache-2.0; no separate dataset license was found in the inspected tree.
Retain its license and attribution when using the release.

The project, dataset, and run pages were reachable. Public raw downloads of
the manifest, license, runner, dataset loader, all three histories, and one
task per persona succeeded. The recursive Git tree lists 200 task YAMLs per
persona. All seven downloaded files covered by the upstream manifest matched
their SHA-256 entries. This verifies availability and sampled integrity; the
remaining tasks and runtime dependencies still require full verification
before execution. No upstream agent or judge was run.

SHA-256 of raw file bytes at that commit:

| Path | SHA-256 |
| --- | --- |
| `manifest.json` | `40107f293243a6cb3941c16e75ce2e3495ed31c68a1015b8537efeb8dfec2ae9` |
| `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `harness/runner.py` | `e3527f38ce716a09671b20918d2b679821a690bbd8e89d14c7cc5e0482fa838c` |
| `harness/dataset.py` | `a790ca29c556fd152947b836fd084006c521e6d52522d0cd98be7bc53c5431c9` |
| `registry/personas/alex/life_sim.yaml` | `e3426b5094e9f2f1adc2c60883ec0eca33c7120a4fa7b8d8f11cad90ce862c18` |
| `registry/personas/morgan/life_sim.yaml` | `4ece5cdf45d89e0d12ac9c76871f6362e32cc185eca68e2c1016244006873356` |
| `registry/personas/riley/life_sim.yaml` | `3d7928715e1229fee16b653ec114c2eb0903831ecdc90513614ced91cf21a9b6` |

The pinned [manifest](https://github.com/mem0ai/dolphinbench/blob/81cb6f8405b40a9e76089cef650806a80af06ea2/manifest.json)
contains 637 file checksums, including every task. Verify its own hash first,
then verify every listed file and shared app-state reference before a run.
Also record the full checkout commit, harness tree
`c89227ed6d7159229ad77d5f62fd42b5650649b4`, dependency lock, AutoMem server
revision, adapter revision, and model/judge configuration in the run manifest.

### Adapter implementation acceptance (still pending)

- Enforce loopback-only AutoMem endpoints (`127.0.0.1`, `::1`, or localhost
  resolving only to loopback); reject non-loopback destinations and redirects
  before sending tokens. The existing backend accepts arbitrary endpoints;
  it does **not** implement this validation yet.
- Require a fresh run/configuration tag plus exact persona tags on every
  write, recall, relation fetch, and deletion. Reject reused/nonempty scopes;
  the scaffold's fixed default scope is insufficient for a real run.
- Compare plain `/recall` with bounded graph expansion under identical
  histories, models, prompts, retrieval budgets, retries, and seeds. Restrict
  every expanded UUID to the same run/persona scope; count extra calls and
  context. Do not assume server expansion bypasses tag gates. Give the agent
  only its request, app tools, and retrieved context, without gold hints.
- Persist returned memory UUIDs, source-message mappings, relation IDs, scope
  tags, and durable per-persona checkpoint identities in a run manifest.
  Freeze completed memory; exclude write tools during tests and verify the
  checkpoint before each fresh conversation with isolated app state.
- Implement resumable cleanup from that manifest only. Verify each UUID's
  exact ownership before deleting, log every result, and retain unresolved
  IDs after partial failure. Verify absence afterward. Never bulk-delete by
  the shared `dolphinbench` tag or touch unrelated memories.
- Preserve chronological ingestion and upstream grading. Pin the paid
  answerer/judge and test their availability before a scored subset; a subset
  is internal diagnostics and cannot stand in for the 600-task submission.

### Reporting acceptance

Publish task-completion accuracy with passed/attempted/expected counts per
persona and overall; report missing tasks, failures, and skips explicitly.
Report total cost in USD across ingestion and testing, with separate phase
totals and disclosed agent, embedding, enrichment, and judge charges. Record
API usage and pricing provenance; unknown charges must not become zero.
Report upstream median task latency in seconds including tool calls, with
sample count and separately labeled ingestion/recall timing diagnostics.
Disclose model/judge revisions, prompts, budgets, retries, and concurrency.

If model or judge access fails, emit `status: not_scored`, the exact blocker,
and null headline accuracy/cost/latency. Preserve measured partial usage and
timings as diagnostics without projecting them into a complete result. Paper
baselines are external references, never AutoMem scores. Protocol doubles and
offline smoke remain unscored. Official benchmark claims stay in `automem`
under [the repository boundary](../../REPO_BOUNDARY.md).
