# External baseline publishing handoff (unsubmitted)

Prepared 2026-10-24. External writes are reserved for the orchestrator. Recheck upstream searches before posting. These drafts do not authorize a benchmark run or spend.

## Comment for automem-evals #45

Target: https://github.com/verygoodplugins/automem-evals/issues/45 (extend the existing follow-up; do not reopen or duplicate).

Added the [external-baseline matrix](https://github.com/verygoodplugins/automem-evals/blob/main/docs/eval/external-baselines-2026-10-24.md) and [JSON](https://github.com/verygoodplugins/automem-evals/blob/main/docs/eval/external-baselines-2026-10-24.json), checked October 24. Publish these main links after merge, or replace them with the finalized PR head before posting.

past.dev reports DolphinBench 490/600 with Hermes and 520/600 with its own agent; these are separate configurations. Its BEAM claims are 92.08/89.63/90.65/85.03 across 100K/500K/1M/10M. Mem0's four headline claims and all 12 currently published RonsenbergVI AMB rows are recorded with owners, answerers, judges and canonical sources. Vendor claims are **unverified field reports**; undisclosed models stay null. No AutoMem scores were created.

Related: #54 remains LongMemEval-V2; PR #73 associates the older agentmemorybenchmark.ai AMB summary, distinct from RonsenbergVI's benchmark. [FEB-30](https://arxiv.org/abs/2610.22209v1)'s average 16pp intrinsic/extrinsic divergence supports PR #61's separate store/retrieval/generation attribution; #74 already tracks FEB-30's blocked release.

No upstream AutoMem new-system issue or PR was found. The proposal below follows [AMB #274](https://github.com/RonsenbergVI/agent-memory-benchmarks/issues/274): use direct memory ingestion/search, bypass the answering proxy, disclose memory-internal models. This matrix extends existing work rather than opening another local benchmark tracker.

## Upstream AMB new-system issue draft

Destination: https://github.com/RonsenbergVI/agent-memory-benchmarks/issues/new?template=new_system.yml

Title: `[new system]: AutoMem`

### Project name

AutoMem

### Repository URL

https://github.com/verygoodplugins/automem

### License

MIT (verified against the public repository LICENSE).

### Memory model

Persistent graph + vector memory with temporal metadata and typed associations; direct HTTP memory-write and recall interfaces.

### Inclusion criteria

- [x] Agent memory is a primary concern of the project, not an afterthought.
- [x] Publicly accessible (OSS).
- [x] Reasonable maintenance signal in the last six months (public main inspected October 24).
- [x] Permissively licensed (MIT).

### Anything else reviewers should know?

The adapter would implement AMB's `ingest_session` via direct `POST /memory` and `search` via `GET /recall`, bypassing any answering-model or chat-proxy loop during ingestion, as required by #274. AutoMem has these direct interfaces, so answering-proxy-only ingestion is not required. Memory-internal extraction, enrichment, embedding and reranking calls still need model pinning and usage accounting; bypassing the answerer does not mean ingestion has zero model cost.

Before an adapter PR: pin AutoMem/server/harness revisions and shared supported models; inspect async ingestion completion; retain session provenance in every hit; cap each search at k; isolate run/session scopes; implement owned-record cleanup and remote-call spend tracking. Report supported model configuration or a blocker rather than silently substituting models. Keep the question agent and judge under AMB control. No adapter, reproducibility run or AutoMem leaderboard score is claimed by this proposal.

### Would you be able to contribute the adapter yourself?

Maybe, with some guidance. This draft proposes inclusion and does not promise an implemented adapter or funded run.

## PR body draft

Record 22 external-baseline references in Markdown and JSON with source URLs, reporting owners, model/judge disclosure, original units and configuration scope. Label past.dev/Mem0 vendor figures as unverified field reports and pin AMB's complete current 12-row table. Distinguish the two AMBs and connect FEB-30's 16pp divergence to PR #61 without asserting AutoMem results.

Related: #45, #54, #61, #73, #74. Includes an unsubmitted #45 comment and upstream new-system proposal; external writes are deferred to the orchestrator. No experiment ran, so no experiment result or dashboard score is registered.

Verification: Python 3.12.13 runner suite 233 tests (13 skipped), scripts suite 30 tests, benchmark-adapter suite 7 tests, and matrix pytest suite 12 tests all pass. JSON parsing, 22-row Markdown/JSON/source-table consistency, canonical HTTPS URL fields, unknown-model nulls and whitespace checks pass. A headless Chromium documentation preview has 22 data rows, working relative JSON/handoff links, readable table overflow and saved screenshot/DOM evidence. See [verification report](external-baselines-verification.md) for commands and limitations.
