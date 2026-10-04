# Shared-memory governance scout

## Decision

Track shared-memory governance as a separate evaluation axis: it asks whether a
candidate write may enter a shared store, and whether a requester may consume a
stored record.  It is not another current-state or forgetting benchmark.

**Go first with GateMem, after a protocol review and a small official smoke
subset.** Its authors released both the benchmark toolkit and data.  **Do not
implement CPB or CoMemBench adapters yet:** no official code or dataset artifact
was located for either as of 2026-10-04.  In particular, do not construct a
synthetic stand-in, and do not publish an AutoMem score for either blocked source.

This scope is adjacent to, but does not duplicate:

- [#31](https://github.com/verygoodplugins/automem-evals/issues/31), which tests
  explicit single-store forgetting controls;
- [#50](https://github.com/verygoodplugins/automem-evals/issues/50), which tests
  current versus superseded state and is itself artifact-blocked;
- [#53](https://github.com/verygoodplugins/automem-evals/issues/53) and
  [#55](https://github.com/verygoodplugins/automem-evals/pull/55), which cover
  action-producing lifecycle evaluation; and
- [#29](https://github.com/verygoodplugins/automem-evals/pull/29), which pins
  exact per-user recall scope for the Agent Memory Leaderboard contract.

The new track instead evaluates admission provenance, multi-principal read and
write authority, and topology-conditioned sharing/isolation.  It must not be
described as a security guarantee: the current AutoMem API has no native admission
gate or lineage-collapse primitive.

## Source and artifact status

The matrices use a ten-point scale. `effort` is implementation effort (10 is most
expensive); all other dimensions are more favorable at higher values. Scores are
scoping judgments, not benchmark results.

### Correlated Promotion Benchmark (CPB)

Primary source: [arXiv:2609.30813](https://arxiv.org/abs/2609.30813), *A Benchmark
and Diagnostic Study of Epistemic Admission in Shared Agent Memory*, submitted
2026-09-25, revision `v1`.

| Dimension | /10 | Rationale |
| --- | ---: | --- |
| source_quality | 8 | Primary preprint with a defined frozen split and live protocol. |
| recency | 10 | Submitted 2026-09-25. |
| automem_fit | 10 | Directly tests the missing write-path admission and provenance boundary. |
| reproducibility | 1 | No official runnable artifact is available to pin. |
| leverage | 10 | Adds correlated-source false-adoption diagnostics unavailable in current tracks. |
| effort | 7 | Requires admission decisions, lineage capture, and a consumer probe. |

| Artifact | Status | URL / revision / license |
| --- | --- | --- |
| CPB-Static frozen split | **Blocked — no official code or dataset release located** | Paper: [arXiv v1](https://arxiv.org/abs/2609.30813). No release URL, artifact revision, or artifact license to record. |
| CPB-Live shared-store environment | **Blocked — no official code or dataset release located** | Same status; do not infer a loader or reconstruct scenarios from the paper. |

The paper defines `promote`, `request_evidence`, `keep_private`, and `abstain` as
admission actions. Its reported figures are paper results, **not AutoMem scores**:
source-type gating has false adoption `0.06–0.09` versus `0.22–0.47` for the other
policies, and a consumer asserts an uncontested false belief in `0.97–0.99` of
probes. The arXiv record describes CPB-Static as frozen and CPB-Live as a
multi-agent shared store, but neither the record nor targeted exact-title searches
found an author code repository, dataset, DOI dataset, or Hugging Face release.

No `runners/cpb/` scaffold is added: the condition for it—an official
CPB-Static artifact—has not been met. Revisit only when its split, gold actions,
loader schema, revision/checksum, and license are released.

### GateMem

Primary source: [arXiv:2606.18829](https://arxiv.org/abs/2606.18829), *GateMem:
Benchmarking Memory Governance in Multi-Principal Shared-Memory Agents*, submitted
2026-06-17, revision `v1`.

| Dimension | /10 | Rationale |
| --- | ---: | --- |
| source_quality | 9 | Primary paper plus author-linked code, data, protocol, and scorer. |
| recency | 9 | Submitted 2026-06-17. |
| automem_fit | 9 | Direct fit for requester, role, scope, relation, leakage, and deletion behavior. |
| reproducibility | 9 | Public episodes/checkpoints and external-prediction scorer are released. |
| leverage | 9 | Couples authorized utility, access violations, and active forgetting. |
| effort | 8 | Needs a policy adapter and structured answer/action production. |

| Artifact | Status | URL / revision / license |
| --- | --- | --- |
| Benchmark toolkit | **Official, available** | [rzhub/GateMem](https://github.com/rzhub/GateMem), commit [`603f9f4b4ba4b77f043c20f85687fa016fd720b0`](https://github.com/rzhub/GateMem/tree/603f9f4b4ba4b77f043c20f85687fa016fd720b0), MIT. |
| Dataset | **Official, available** | [Ray368/GateMem](https://huggingface.co/datasets/Ray368/GateMem), revision `b4304866ec8d9784fb77bebb1ce4660806abcded`, CC-BY-4.0. |

GateMem evaluates utility for authorized requests, access-control leakage across
roles/scopes/relations, and active forgetting after deletion requests. Its official
external-scoring contract accepts a `predictions.jsonl` keyed by `checkpoint_id`.
That makes it the first implementation candidate, but no AutoMem result is claimed
here.

### CoMemBench

Primary source: [arXiv:2609.32192](https://arxiv.org/abs/2609.32192), *CoMemBench:
Benchmarking Collaborative Memory Boundaries across Multi-Agent Workflow
Topologies*, submitted 2026-09-26 and revised 2026-09-29, revision `v2`.

| Dimension | /10 | Rationale |
| --- | ---: | --- |
| source_quality | 8 | Primary preprint with an execution-grounded benchmark design. |
| recency | 10 | Current revision is 2026-09-29. |
| automem_fit | 8 | Tests handoff validity and isolation beyond ordinary recall. |
| reproducibility | 1 | No official runnable artifact is available to pin. |
| leverage | 9 | Adds topology-conditioned visibility and intermediate-artifact validity. |
| effort | 9 | Requires reproducing workflow executors and native evaluators unchanged. |

| Artifact | Status | URL / revision / license |
| --- | --- | --- |
| Workflows, graphs, evaluators, and data | **Blocked — no official code or dataset release located** | Paper: [arXiv v2](https://arxiv.org/abs/2609.32192). No release URL, artifact revision, or artifact license to record. |

The paper describes 800 workflows with node-local specifications, verifiable
handoffs, matched isolation challenges, and native evaluators. Those elements are
not reproducible from the paper alone. Its arXiv record has no author artifact link,
and targeted exact-title/author searches found no official repository, dataset,
DOI dataset, or Hugging Face release. Do not turn its described workflows into a
synthetic benchmark or report an AutoMem score.

## AutoMem mapping and capability boundary

| Governance construct | Adapter treatment | Current limitation / assertion |
| --- | --- | --- |
| Isolated evaluation run | Add generated run and episode tags to every record, and send both with source-derived visibility tags using `tag_match=exact` and `tag_mode=all` on every recall. | Test the returned request parameters; exact matching avoids prefix scope bleed, `all` prevents the shared run tag alone from authorizing a record, and episode tags prevent reset leakage. |
| Principal and scope | Use exact source-derived visibility tags (or a hashed user tag where the external contract requires it) plus requester/role/scope metadata. | Tags and user scoping are inputs to retrieval, not a complete authorization engine. |
| Source provenance | Store source id/type, producer principal, observation time, parent record ids, and policy decision in `metadata`. | Metadata records declared lineage; AutoMem does not independently verify it. |
| CPB admission decision | A CPB adapter emits `promote`, `request_evidence`, `keep_private`, or `abstain` before any shared write. | **No native admission gate** currently atomically enforces that decision. |
| GateMem ingestion | A GateMem adapter ingests each official non-lifecycle episode turn unchanged; its official actions occur at checkpoints. | Do not invent CPB-style admission labels or drop source turns. |
| Revision and deletion provenance | Use `supersedes_memory_id`, `INVALIDATED_BY` (old → new), and `t_invalid`; preserve the audit record. | This controls lifecycle state but does not automatically collapse all derived or paraphrased lineage. |
| Correlated copies / derived artifacts | Retain explicit parent/source ids in metadata and make the adapter inspect them before promotion or handoff. | **No native lineage-collapse** exists today. A copied or paraphrased record is not automatically joined to its source. |
| Leakage audit | Save retrieved ids, policy input, final action, and any answer/redaction decision per official checkpoint. | A diagnostic adapter cannot certify confidentiality outside its tested path. |

## Proposed adapter protocol

Use this protocol only with an official source release; each adapter must preserve
the source’s episode order, hidden fields, scoring implementation, and native
evaluators.

1. **Pin and isolate.** Record upstream URL, immutable revision, license, dataset
   checksum, model/prompt/seed, a generated `smg-run-<uuid>` tag, and a distinct
   `smg-episode-<id>` tag for every official episode. Include both tags on every
   write and recall; an episode reset must not retrieve records from an earlier
   episode. Reject every non-local AutoMem endpoint.
2. **Encode authority and lineage before writing.** For every input, derive only
   the source-provided principal/role/scope/relation and attach them as metadata.
   Materialize exact record-level visibility tags only from source policy events;
   maintain those tags when the source changes a delegation, assignment, or
   relationship. At recall, require the generated run and episode tags plus the
   applicable source-derived visibility tags with `tag_match=exact` and
   `tag_mode=all`.
   Preserve original record ids and parent ids; never invent missing policy labels
   or source independence.
3. **Preserve source-specific write semantics.** A CPB adapter applies its
   source-provided `promote`, `request_evidence`, `keep_private`, or `abstain`
   decision before a shared write: only `promote` can create shared memory;
   `keep_private` may write only to an explicitly private namespace; the other
   actions leave no shared claim behind. A GateMem adapter ingests every
   non-lifecycle episode turn unchanged and uses only GateMem's official
   checkpoint-time actions (`answer`, `answer_redacted`, `refuse`, or
   `no_memory`). Log the applicable source action even when no write occurs.
4. **Retrieve under declared requester scope.** Recall with the run, episode, and
   source-derived visibility constraints using `tag_match=exact` and
   `tag_mode=all`; retain returned ids and raw policy inputs. Apply the
   source-provided authorization/visibility rule before the answer layer, and emit
   the official action/answer shape without exposing hidden labels to that layer.
5. **Process lifecycle events explicitly.** For an official update, use the MCP
   `supersedes_memory_id` surface, or expand it into: fetch the old record, store
   the replacement, patch `t_invalid` on the old record, and create the old → new
   `INVALIDATED_BY` edge. Verify that sequence. For an official deletion, set
   `t_invalid` on the active record without writing a replacement or retrievable
   tombstone. Record any unresolved dependent/derived record as a limitation rather
   than claiming lineage collapse.
6. **Score only with the official evaluator.** Keep source categories and
   denominators intact. Report source revision, run tag, action trace, retrieval
   trace, all exclusions, and the cold/matured status; never translate paper
   baselines into AutoMem results.

For GateMem specifically, first validate the official loader and external scorer
at the pinned revisions, then add a small official smoke subset containing each of
utility, access control, and active forgetting. Unit tests should cover exact
run/episode/visibility tag scope, reset isolation, unauthorized-request
denial/redaction, unconditional non-lifecycle GateMem turn ingestion, lifecycle
edge direction, and refusal to score an unpinned or non-local run. A CPB adapter
should separately test no shared write for a non-`promote` action.

## Cold versus matured reporting

Follow [the repository maturation contract](maturation.md) for every curated
result. Each result must report `cold` and `matured` separately; `matured-full` is
separate when used. `cold` is the comparable immediate-ingest result. `matured`
drains enrichment and runs the frozen narrative-time profile with the same
checkpoint as-of guard; it must not see future writes or future permissions.

Until narrative-clock `/consolidate` support exists, label the result `cold` and
record `matured: blocked` with the dependency. Never call a cold run mature, pool
the variants, or hide an access/admission failure in an aggregate score. In this
track, preservation must also include the exact authorization and provenance
metadata presented to the adapter at each checkpoint.

## Go/no-go order

1. **Go — GateMem.** Pin the released MIT toolkit and CC-BY-4.0 data, validate the
   official loader/scorer from a clean checkout, then implement a local-only
   adapter and smoke subset. No score is authorized before that validation.
2. **No-go pending artifacts — CPB-Static / CPB-Live.** Poll for author-released
   split/environment, gold action schema, immutable revision/checksum, and
   license. Add `runners/cpb/` only after CPB-Static is official and pinned.
3. **No-go pending artifacts — CoMemBench.** Wait for the official workflows,
   dependency graphs, topology definitions, native evaluators, immutable revision,
   and license. Do not approximate its artifact-validity or isolation challenge.

This ordering reflects artifact availability, not a claim that GateMem subsumes
CPB’s admission-lineage or CoMemBench’s topology-boundary questions.
