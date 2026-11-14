# MemDelta-style controlled baselines for AutoMem

## Purpose

This protocol makes an attribution claim narrow enough to test: change one
memory-system component while holding the answerer, judge, embedding model,
dataset split, random seed, and retrieval budget fixed. It applies the
controlled-baseline guidance in [MemDelta](https://arxiv.org/abs/2606.29914) to
AutoMem experiments. It is a protocol for internal evaluation artifacts, not a
replacement for the canonical benchmark harnesses or a source of official
leaderboard claims.

MemDelta found that an embedding-only swap changed LongMemEval-S accuracy by
6.2 points, and that apparent memory-system advantages can reverse by reader
family. Its 50x-cost result for a narrow Mem0 comparison is a reminder to
report the write path beside accuracy, not an AutoMem result. The protocol also
carries forward the incremental, multi-turn competencies from
[MemoryAgentBench](https://arxiv.org/abs/2507.05257), and the action-grounding
surface of [Mem2ActBench](https://aclanthology.org/2026.acl-long.370/).

## Pre-registration and common controls

Before any scored run, record the dataset revision/checksum, split, seed,
AutoMem commit/image, hardware, timeout/retry policy, context budget, top-k,
prompt templates, reader snapshot, judge snapshot, and stopping rule. Keep
the same source conversation and question set in every compared cell.

Use a fixed embedding model as the primary comparison condition. Record its
provider, model revision, dimensions, and vector normalization. Run AutoMem's
configured default embedding separately as a sensitivity condition; it must
not be pooled with the fixed-embedding result or used to attribute a graph or
retrieval effect. Unknown version data is reported as `null`, never as a
guessed version.

Run each reader family separately (at least one pinned model per available
OpenAI, Anthropic, and Google family). Report scores by family and question
type, then a macro average only when every family has the same cells. Do not
call an average a model-independent result.

## Baseline arms

Every reader-family × fixed-embedding block includes these arms:

| Arm | Write path | Read path | What it controls |
| --- | --- | --- | --- |
| `no-memory` | none | no historical context | reader-only floor |
| `verbatim-rag` | fixed, chronological text chunks | same fixed embedding, same top-k/token budget | retrieval without memory transformation |
| `full-context` | no index | complete eligible history, truncated only by the declared context rule | retrieval-index tradeoff |
| `automem` | AutoMem ingest | AutoMem recall at the same top-k/token budget | full system |

`full-context` must use the raw eligible history, not a pre-summarized proxy.
`verbatim-rag` must not add graph edges, LLM extraction, or a different chunker
unless that is the explicitly named ablation. The no-memory arm still gets the
same task instruction and reader model.

## AutoMem ablation matrix

The architecture matrix is run only inside an `automem` arm after the baseline
block is complete. Start from **C0** and change exactly one switch per next
row. Repeat the complete set per reader family and embedding condition.

| Cell | Embedding | Graph edges written | Recall relation expansion | Attribution |
| --- | --- | --- | --- | --- |
| C0 | fixed | off | off | plain AutoMem substrate |
| C1 | fixed | on | off | write-time graph-edge effect |
| C2 | fixed | on | on | read-time expansion effect relative to C1 |
| S1 | AutoMem default | off | off | embedding-default sensitivity, not an architecture comparison |
| S2 | AutoMem default | on | off | sensitivity for C1 |
| S3 | AutoMem default | on | on | sensitivity for C2 |

For `on`, declare the exact edge inventory and creation policy. The initial
coverage includes `RELATES_TO`, `INVALIDATED_BY`, `EVOLVED_INTO`,
`OCCURRED_BEFORE`, `PART_OF`, and `REINFORCES` when a benchmark's ground truth
permits them; never silently add inferred edges to one cell. Report each edge
type's count and failures. `off` means no association write, not merely
disabling expansion.

Expansion means the explicit `expand_relations` read setting and its hop/limit
policy. In this repository, tag gating can filter expansion targets and make
server-side expansion a no-op. Therefore each C2/S3 artifact must include the
number of returned expansion-only memories. A zero count is a valid finding,
not proof that graph edges have no value; use the existing client-side expansion
prototype when testing an ungated traversal hypothesis.

The matrix is intentionally not a full cross-product of unrelated knobs. Do
not alter chunking, reranking, time filters, entity expansion, prompt wording,
or top-k while moving from C0 to C2. Those require a new, named one-variable
block.

## Required results metadata and cost reporting

Store the `metadata.controlled_evaluation` block defined by
[`memdelta-controlled-results.schema.json`](memdelta-controlled-results.schema.json)
in every result. It records the embedding model and mode, reader model and
family, judge profile, graph and expansion settings, and write-path cost.

Write-path cost is reported per run and normalized per source token, memory,
and task where meaningful:

- input/output tokens spent during ingestion, extraction, consolidation, and
  edge creation;
- wall-clock write latency (total plus median/p95 when per-write timings exist);
- memory writes, association writes, and enrichment/consolidation calls;
- provider/model usage and any retries or failures.

`null` means the runner cannot observe a measurement. List it in
`unavailable_measurements`; do not substitute zero. Retrieval latency, context
tokens, and answer/judge usage remain separate read-path measures.

The existing `beam-judged` runner now emits this block and supports metadata
flags for embedding mode, reader family, graph-edge writes, and relation
expansion. Its current sequential-edge implementation records
`OCCURRED_BEFORE`; benchmark adapters add other declared types only when their
write policy is implemented.

## Execution targets

1. **LongMemEval-S.** Run via the canonical AutoMem harness in the sibling
   `automem` repository at `tests/benchmarks/longmemeval`, pinned to a commit.
   Use the 500-question LongMemEval-S split, all six question types, and report
   paired per-question deltas plus confidence intervals.
2. **Mem2ActBench.** Run the repository's Mem2ActBench adapter (introduced in
   [PR #34](https://github.com/verygoodplugins/automem-evals/pull/34)) against
   the upstream runner. Preserve its end-to-end tool-call/parameter-grounding
   score and separately label any evidence-retrieval proxy; a proxy is not
   comparable to the benchmark's action metric.

Execution is tracked in [#48](https://github.com/verygoodplugins/automem-evals/issues/48).
The tracking issue for these runs must link the pinned harness revisions,
licenses, command lines, raw-result retention location, and the generated
schema-valid reports. Do not commit benchmark datasets or raw private run
artifacts to this repository.

## Interpretation rules

- Compare C1 with C0 for graph write value; compare C2 with C1 for expansion.
  Do not compare C2 directly with C0 and attribute all movement to expansion.
- Make statistical claims from matched per-question outcomes, stratified by
  reader family and question type. Include sample count, uncertainty interval,
  and failures/exclusions.
- If the embedding, reader, judge, prompt, context policy, or write path differs,
  label the result exploratory rather than a controlled head-to-head.
- Publish accuracy with write-path cost and read-path latency/context. A cheaper
  baseline that matches an architecture on most task types is a result worth
  reporting.

## Sources

- Kuan Wang, [*MemDelta: Controlled Baselines and Hidden Confounds in Agent
  Memory Evaluation*](https://arxiv.org/abs/2606.29914), arXiv:2606.29914,
  2026.
- Yiting Shen et al., [*Mem2ActBench: A Benchmark for Evaluating Long-Term
  Memory Utilization in Task-Oriented Autonomous Agents*](https://aclanthology.org/2026.acl-long.370/), ACL 2026.
- Yuanzhe Hu, Yu Wang, and Julian McAuley, [*Evaluating Memory in LLM Agents
  via Incremental Multi-Turn Interactions*](https://arxiv.org/abs/2507.05257),
  arXiv:2507.05257.
