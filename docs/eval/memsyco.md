# MemSyco-Bench — memory-use authority evaluation

## Decision and status

Track [MemSyco-Bench (arXiv:2607.01071v2)](https://arxiv.org/html/2607.01071v2)
as an experimental evaluation of memory-induced sycophancy and bias propagation.
Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.
As of **2026-10-25**, dataset, harness, and leaderboard are public. AutoMem is
**`not_scored`**, with all score/rate fields **null**. This slice supplies an
adapter plan and real upstream data/harness preflight, not an AutoMem runner.

The immediate blocker is a published manifest mismatch for Objective Fact
Judgment. The other four files match; all 1,550 rows load. The upstream release
test fails, so do not silently repair the manifest or claim release integrity.
A scored AutoMem run also requires the adapter below and pinned reader/judge
configuration. See [commands and results](memsyco-verification.md) and
[issue/PR handoff](memsyco-handoff.md).

## Public artifact check

| Artifact | Verified source and status |
| --- | --- |
| Paper | [HTML v2](https://arxiv.org/html/2607.01071v2), including the five memory-use tasks and links to author code/board. |
| Code/data | [Author repository at `3c3aa013ac5bee2f0e252fe8748644edc7f9af0a`](https://github.com/XMUDeepLIT/MemSyco-Bench/tree/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a), MIT license; dependency-free loader, JSONL files, manifest/schema 1.2, task runners and judges. |
| Data mirror | [Author Hugging Face dataset](https://huggingface.co/datasets/MemSyco-Bench/MemSyco-Bench), public; smoke uses the pinned GitHub release, not an unpinned mirror. |
| Leaderboard | [Live author board](https://xmudeeplit.github.io/MemSyco-Bench-Leaderboard/) and [source at `84125959cb7db8af442783d4b063f39bd4267229`](https://github.com/XMUDeepLIT/MemSyco-Bench-Leaderboard/tree/84125959cb7db8af442783d4b063f39bd4267229). Public comparison surface; no AutoMem submission was made. |

The all-state issue/PR search found no existing MemSyco/sycophancy tracker.
Adjacent work remains separate: #50 StateMemBench (operative state), #51 MemTrace
(evidence use), #62/PR #63 Veracium (validity/provenance), and PR #61 EvalMem
(operation diagnostics). Retrieval success alone cannot establish appropriate
memory use, and invalidating every preference would fail valid personalization.

## AutoMem adapter plan

Implement a local adapter for upstream `build_baseline_context(prior_dialogue,
user_question, eval_config, sample_key=...)`, returning `BaselineContext`
(`context_text`, `retrieved_memories`, `user_id`, `save_dir`, `method`, `top_k`).
Register it as an explicit experimental AutoMem method in a disposable upstream
checkout. Preserve upstream generation prompts, task judges and aggregation.
Keep dependency-heavy upstream execution outside this stdlib-only repository.
Source contracts: [baseline API](https://github.com/XMUDeepLIT/MemSyco-Bench/blob/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a/baselines/base.py),
[registry](https://github.com/XMUDeepLIT/MemSyco-Bench/blob/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a/baselines/registry.py),
and [data card](https://github.com/XMUDeepLIT/MemSyco-Bench/blob/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a/data/README.md).

Replay **only dialogue**, in order, into an isolated local AutoMem bank, retaining
sample, speaker, turn, source and scope provenance. Query `/recall` with the
current `question`, a unique run/sample tag and frozen `limit=top_k`; record IDs,
scores, validity bounds, lifecycle edges, context order and truncation. Gold
`memory` items/policies/statuses and `evaluation` references/rubrics stay on the
evaluation side. Neither ingestion nor recall may use them to choose operations.
Any gold-memory diagnostic must be labelled **oracle**, outside the ordinary arm.

| Decision role / released task | Recall and answer contract | Diagnostic |
| --- | --- | --- |
| Reject / `objective_fact_judgment` (300) | A recalled user belief remains an attributed belief, not factual evidence. Reader answers from factual support; retrieval need not delete the belief. | Official accuracy and sycophancy; distinguish belief retrieved from belief followed. |
| Constrain / `contextual_scope_control` (300) | Carry subject/audience/scope from dialogue into recalled context. Reader limits preference use to compatible constraints. | Official accuracy and sycophancy; log scope transfer even when semantic retrieval succeeds. |
| Update / `valid_memory_selection` (350) | Compare plain replay with a frozen dialogue-driven revision detector using `supersedes_memory_id=<old-id>` on replacement writes. | Official accuracy and outdated-preference use; separately audit current retrieval and stale leakage. |
| Reconcile / `memory_evidence_conflict` (300) | Preserve provenance for preference and current evidence; reader prioritizes stronger evidence. A task-specific conflict need not globally invalidate a still-valid preference. | Official accuracy and sycophancy; record evidence retrieved/used independently. |
| Leverage / `personalized_memory_use` (300) | Recall applicable valid preferences and personalize within current constraints. | Official accuracy and correct-preference use; detect over-suppression. |

### Temporal validity, supersession and abstention

Use `t_valid`/`t_invalid` for fact validity, not wall-clock ingestion time. When
the dialogue supplies only ordering, preserve turn ordinals and label any
synthetic replay clock; do not invent source dates. Verify replacement writes
close the old interval and create `INVALIDATED_BY` **old → new**; distinguish
evolution via `EVOLVED_INTO` **old → new** when supported. Audit stored records
and suppression rather than assuming metadata enforces behavior. Freeze
`current_only=true` for the current-preference arm; use `current_only=false`
only for a separately labelled history diagnostic, with no future-turn leakage.

Empty recall is not answer abstention. Record empty retrieval, explicit
insufficient-evidence/clarification responses, and task correctness separately.
Do not treat abstention as a universally correct answer: apply the official
rubric, which may require correction or valid personalization. Missing/failed
judge calls yield `not_scored` and null rates, never zero or automatic success.

## Scored-run acceptance

- Resolve the integrity mismatch via an attributable author revision; pin code,
  dataset checksums, license, schema, reader/extractor/judge models and prompts,
  top-k/context budget, seed/retry policy, and selected sample IDs.
- Add adapter tests for gold leakage, scope/provenance, temporal boundaries,
  old→new supersession, abstention and error accounting. Reject non-loopback
  endpoints and redirected writes; clean only manifested run-owned IDs.
- Run one real sample per task against isolated local AutoMem, then expand only
  after checking upstream scorer output. Include `NoMemory` and `RawDialogue`
  controls with identical reader/judge settings. Report per-task denominators
  and official metrics; retrieval diagnostics are not benchmark scores.
- Follow [maturation.md](maturation.md): report `cold` and `matured` separately,
  mark unsupported maturation blocked, and never pool modes or compare paper
  baselines as AutoMem results. Official claims remain in `automem`.
