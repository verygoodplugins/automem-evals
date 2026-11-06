# External memory baseline references — 2026-10-24

Reference snapshot for `opportunity:automem-graph-rag-research-scout`, not an AutoMem evaluation. [Machine-readable matrix](external-baselines-2026-10-24.json). Owner means the run/claim reporter; AMB system ownership is recorded separately in JSON.

Vendor claims are **unverified field reports**. Upstream publication does not establish independent reproduction here. Unknown model/judge fields are `null` in JSON and “not disclosed” below; current harness defaults cannot fill historical omissions. Scores, denominators and units stay as reported. Do not rank across harnesses, readers, judges, datasets, retrieval budgets or agents.

## past.dev: unverified field reports

| Benchmark / configuration | Reported score | Owner | Answer model | Judge | Canonical source |
| --- | --- | --- | --- | --- | --- |
| DolphinBench / Hermes Agent | 81.7% (490/600) | past.dev | GPT 5.6 Luna (high reasoning) | GPT 5.6 Sol (medium reasoning) + deterministic checks | [source](https://past.dev/benchmarks/dolphinbench) |
| DolphinBench / past.dev own agent | 86.7% (520/600) | past.dev | GPT 5.6 Luna (high reasoning) | GPT 5.6 Sol (medium reasoning) + deterministic checks | [source](https://past.dev/benchmarks/dolphinbench) |
| BEAM / 100K | 92.08% | past.dev | openai/gpt-5.6-luna (reasoning off) | openai/gpt-5.6-luna (reasoning off) | [source](https://past.dev/benchmarks/beam) |
| BEAM / 500K | 89.63% | past.dev | openai/gpt-5.6-luna (reasoning off) | openai/gpt-5.6-luna (reasoning off) | [source](https://past.dev/benchmarks/beam) |
| BEAM / 1M | 90.65% | past.dev | openai/gpt-5.6-luna (reasoning off) | openai/gpt-5.6-luna (reasoning off) | [source](https://past.dev/benchmarks/beam) |
| BEAM / 10M | 85.03% | past.dev | openai/gpt-5.6-luna (reasoning off) | openai/gpt-5.6-luna (reasoning off) | [source](https://past.dev/benchmarks/beam) |

- DolphinBench: Hermes is self-administered and absent from the official board; the own-agent result is a separate configuration. The vendor reports test-toolset selection after experiments on the same tasks, without a held-out set. Its Hermes evidence exceeds packaging limits; the own-agent submission awaits validation.
- [October 20 press release](https://www.prnewswire.com/news-releases/memory-for-ai-agents-gets-more-accurate-pastdev-reports-the-highest-score-yet-on-dolphinbench-302914085.html) announces the claims; the numeric rows above come from the linked results page, not an independent PR Newswire evaluation.
- BEAM uses ExaBase-derived prompts, including dataset question-annotation guidance, and the same model answers and judges. It is not a controlled comparison with other vendors.
- [October 6 BEAM release](https://www.prnewswire.com/news-releases/pastdev-introduces-frontier-memory-for-ai-agents-1-on-beam-the-largest-public-memory-benchmark-302899770.html) matches these four tiers, but its image caption and table disagree about prior-best baselines. We do not promote those comparator claims.
- Method disclosures pinned at [pastdotdev/benchmarks a712cd9](https://github.com/pastdotdev/benchmarks/tree/a712cd993e249cadd214168c3c3ee674f89bd5e4): [DolphinBench](https://github.com/pastdotdev/benchmarks/blob/a712cd993e249cadd214168c3c3ee674f89bd5e4/dolphin/README.md), [BEAM](https://github.com/pastdotdev/benchmarks/blob/a712cd993e249cadd214168c3c3ee674f89bd5e4/beam/README.md). This is a source inspection, not a rerun.

## Mem0: unverified field reports

Scope: the post's four 2026-algorithm headline scores, not its secondary competitor table. The post was updated October 10. It links an evaluation repository but does not tie these scores to a reader/judge snapshot, exact dataset revision or aggregation. Preserve its 0–100 score units without assuming a binary pass rate.

| Benchmark | Reported score | Owner | Answer model | Judge | Canonical source |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 92.5 | Mem0 | not disclosed | not disclosed | [source](https://mem0.ai/blog/state-of-ai-agent-memory-2026) |
| LongMemEval | 94.4 | Mem0 | not disclosed | not disclosed | [source](https://mem0.ai/blog/state-of-ai-agent-memory-2026) |
| BEAM (1M) | 64.1 | Mem0 | not disclosed | not disclosed | [source](https://mem0.ai/blog/state-of-ai-agent-memory-2026) |
| BEAM (10M) | 48.6 | Mem0 | not disclosed | not disclosed | [source](https://mem0.ai/blog/state-of-ai-agent-memory-2026) |

## RonsenbergVI Agent Memory Benchmarks (AMB)

Owner/reporter for every row: **RonsenbergVI (René-Jean Corneille)**. Systems: EverOS/EverMind-AI and MemOS/MemTensor. This is distinct from the older `agentmemorybenchmark.ai` Core-3 + BEAM summary in this repository.

All 12 rows in the current [RESULTS.md](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) are transcribed below. Answerer and judge are both `anthropic:claude-haiku-5-5` for every row; ingestion uses that same model, embeddings `openai:text-embedding-3-small`. Status: upstream published result, **not independently rerun**. Accuracy is a fraction, not percent. The report header names memos/v0.3.0 (October 23), but each row represents its latest system/dataset/model run.

| Dataset / variant | System version | k | Questions | Judge accuracy | Canonical source |
| --- | --- | --- | --- | --- | --- |
| locomo | everos 1.4.2 | 10 | 1986 | 0.706 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | everos 1.4.2 | 5 | 1986 | 0.707 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | everos 1.4.2 | 1 | 1986 | 0.603 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | everos 1.4.2 | 3 | 1986 | 0.694 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | memos 2.0.33 | 10 | 1986 | 0.668 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | memos 2.0.33 | 1 | 1986 | 0.487 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | memos 2.0.33 | 5 | 1986 | 0.626 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| locomo | memos 2.0.33 | 3 | 1986 | 0.602 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| longmemeval (xs-shared) | memos 2.0.33 | 10 | 151 | 0.775 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| longmemeval (xs-shared) | memos 2.0.33 | 5 | 151 | 0.755 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| longmemeval (xs-shared) | memos 2.0.33 | 3 | 151 | 0.742 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |
| longmemeval (xs-shared) | memos 2.0.33 | 1 | 151 | 0.609 | [source](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/RESULTS.md) |

[Methodology](https://github.com/RonsenbergVI/agent-memory-benchmarks/blob/3c2aeeafd5fea0ebf00c63db81fb92f6b46dfe91/METHODOLOGY.md): k caps one search; agents may search repeatedly, so k does not equal total hits/question. JSON preserves observed hits/question. Binary answer accuracy differs from memory lift and evidence-session attribution. LongMemEval `xs-shared` (151 questions) is not the 500-question LongMemEval-S protocol or LongMemEval-V2.

## Existing work and handoff

All-state issue and PR searches were performed before writing; no duplicate local tracker is proposed.

| Existing item | Observed state / route |
| --- | --- |
| [#45 DolphinBench](https://github.com/verygoodplugins/automem-evals/issues/45) | Closed; extend its existing implicit-recall follow-up comment with this matrix. Closure covers the protocol scaffold, not a scored run. |
| [#54 LongMemEval-V2](https://github.com/verygoodplugins/automem-evals/issues/54) | Open; distinct web-agent experience benchmark, not these LongMemEval claims. |
| [PR #61 EvalMem](https://github.com/verygoodplugins/automem-evals/pull/61) | Open; store/retrieval/oracle-generation attribution, unscored pilot. |
| [PR #73 dashboard](https://github.com/verygoodplugins/automem-evals/pull/73) | Open; associates the older AMB summary, not a RonsenbergVI submission tracker. Do not conflate the two AMBs. |
| [#74 FEB-30](https://github.com/verygoodplugins/automem-evals/issues/74) | Open; official release blocked. Extend this tracker rather than filing another. |

[FEB-30, arXiv:2610.22209v1](https://arxiv.org/abs/2610.22209v1) reports an average **16 percentage-point** divergence between intrinsic store-level and extrinsic QA scores in its tested representative system. This supports PR #61's attribution approach: inspect encoding/store state, retrieval support and generation separately. It neither validates that implementation nor supplies an AutoMem score.

Upstream AMB all-state searches for `AutoMem` in issues (including comments) and PRs returned no matches on October 24; its current results contain no AutoMem row. Recheck before publishing. [Issue #274](https://github.com/RonsenbergVI/agent-memory-benchmarks/issues/274) is TencentDB's new-system proposal, not AutoMem's: ingestion through an answering proxy is disallowed; direct memory write/search should be used, otherwise inclusion waits.

AutoMem already exposes direct `POST /memory` and `GET /recall`, also used by this repo's [adapter](../../scripts/benchmarks/dolphinbench_adapter.py). A proposed AMB adapter should call these directly, never ask an answering model to process ingestion. Memory-internal extraction/enrichment models remain separate and must be disclosed/pinned, along with asynchronous completion, source session IDs, isolation, cleanup and usage coverage. See the [unsubmitted new-system draft](external-baselines-handoff.md). No AMB adapter or run is claimed here.

Execution boundary: local commit only. The issue comment, upstream proposal and PR body are prepared for the orchestrator; none was posted. No benchmark model calls or AutoMem scores were produced. Official AutoMem claims remain in the product repository per [REPO_BOUNDARY](../REPO_BOUNDARY.md).
