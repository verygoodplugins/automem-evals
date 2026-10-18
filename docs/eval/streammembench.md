# StreamMemBench — streaming evidence and feedback adapter plan

Track [#67](https://github.com/verygoodplugins/automem-evals/issues/67). Related: [StateMemBench #50](https://github.com/verygoodplugins/automem-evals/issues/50), [MemTrace #51](https://github.com/verygoodplugins/automem-evals/issues/51), and [PrecisionMemBench PR #66](https://github.com/verygoodplugins/automem-evals/pull/66). Candidate: `opportunity:automem-graph-rag-research-scout`. MERIT #53 and closed DolphinBench #45 remain separate.

## Source and availability, checked 2026-10-18

[Paper v2](https://arxiv.org/abs/2606.14571v2), accepted to Findings of EMNLP 2026: two-step tasks built from EgoLife streams diagnose evidence recall, initial use, feedback incorporation, and follow-up reuse. The authors' eight-system/two-backbone finding motivates testing whether retrieved evidence actually changes behavior; it is not an AutoMem result.

| Artifact | Pin / availability |
| --- | --- |
| [Official harness](https://github.com/landian60/StreamMemBench/tree/b32965525da5f982599af9794954c616ddeb34ff) | Cloned at `b32965525da5f982599af9794954c616ddeb34ff`; MIT code. |
| Chinese text release | Git tree `7e131a598ce782a55a3e471563a08bba29e9bd0c`; English release also included. |
| Smoke source `data/streammembench_v1/evidence_tasks/A1_JAKE/DAY1.clean.json` | SHA-256 `5ad04c761b5c0af2b024670bda2012a98a728cd1b852cf109356e37d64ed926b`. |
| EgoLife dependency | Converted text/tasks are present; raw video is unnecessary for this smoke. [Upstream dataset card](https://huggingface.co/datasets/lmms-lab/EgoLife) declares MIT; harness README retains EgoLife license/access terms. Cite both projects; participant data stays in the ignored checkout. |

The public metric key `fidelity` audits newly saved records by default; it is not retrieval recall. Keep `saved_records` fidelity separate from the optional `retrieve_probe` mode and from answer-time support retrieval.

## Proposed AutoMem adapter

Implement `runners/streammembench/` against the pinned `src/streammembench/memory/base.py` interface, following #66's isolated-local and audit conventions:

| Hook | Mapping and verification |
| --- | --- |
| `add_stream_to_memory` | Store observations in narrative order, including unscored timeline windows. Use exact per-run/participant tags, source timestamps, and a segment-to-UUID map. Write provenance associations only from observed content. |
| `retrieve_memory` | Call `/recall` with exact isolation and a frozen budget. Preserve rank, noise, UUIDs, and provenance; record retrieved support independently of answer use. Start with current-only retrieval; historical queries require an explicit, separately reported mode. |
| `generate_response` | Fixed reader receives only request plus returned memory context. No gold evidence, expected behavior, supporting spans, or evaluator rationale enters prompts or storage. |
| `generate_response_with_feedback` | Reader sees the actual feedback and initial interaction. Persist a correction only through observed interaction storage; never expose evaluator labels. |
| `store_interaction` | Store request, answer, feedback, and revision once before follow-up. For an explicitly identified factual replacement, associate **old → new** `INVALIDATED_BY` and persist old `t_invalid`; retain history. Acknowledgment or additive feedback must not invalidate prior facts. |
| Inspection / reset / diagnostics | Inspect real saved records for fidelity; clear only adapter-owned UUIDs. Reject non-loopback endpoints/redirects, fail on HTTP/protocol errors, and advertise exact-resume/usage capabilities only after verification. |

Compare plain writes against provenance plus explicit feedback supersession with identical data, reader, prompts, retrieval budget, retries, and seeds. Test edge direction, current-only suppression, history retention, run/participant isolation, no future-window ingestion, feedback idempotency, and label exclusion before a scored AutoMem smoke. Do not assume graph expansion crosses tag gates or guarantees evidence use.

Run a small chronological official-data subset on a dedicated AutoMem stack, retain HTTP and per-item diagnostics, and disclose that the system is AutoMem plus an external reader/adapter. Follow [maturation.md](maturation.md): cold ingestion/indexing first; curated comparisons require a separate frozen-profile matured run with narrative-clock guards. Do not silently substitute one for the other.

## Scoring-rigor contract

[SurrealDB's 2026-10-14 post](https://surrealdb.com/blog/agent-memory-benchmarks-are-baked) motivates publishing strict full-marks scores alongside headline metrics and disclosing the answerer/judge. Preserve upstream aggregation and publish all four metrics with sample counts, feedback-applicable denominator, language, failures/skips, and raw per-item decisions. Disclose exact reader, feedback simulator, fidelity auditor, judge models/revisions, prompts, voting, sampling, context budget, and provider settings; a deterministic component must be identified as such.

At this pin item metrics are binary, so per-metric strict rates equal their headline rates. Additionally report strict trajectory success: every applicable metric equals 1; include fidelity, initial use, follow-up reuse, and feedback incorporation only when applicable. Publish that denominator and a separate feedback-required subset (N/A if empty). Keep raw judgements so any rubric-level full-marks view can be recomputed; disclose when the harness exposes no finer rubric. Do not change the official scorer or rank runs with mismatched models/judges.

## Executed harness smoke; AutoMem not run

On 2026-10-18, fresh `rag_raw` deterministic runs completed the upstream mini fixture and the first official Chinese release item (two evidence anchors each), with zero model/API calls. The release smoke had zero feedback-applicable cases, so it does **not** verify correction or reuse of corrections. This checks harness/data wiring only; no AutoMem score or paper-comparable result is claimed. AutoMem adapter implementation and its cold/matured runs remain follow-up work in #67.

Reproduce from this repository with Python 3.10+ (verified with 3.12.13 and PyYAML 6.0.3). The clean environment prevents inherited API credentials from enabling model calls:

```sh
mkdir -p .agent-drafts/upstream
git clone https://github.com/landian60/StreamMemBench .agent-drafts/upstream/StreamMemBench
git -C .agent-drafts/upstream/StreamMemBench checkout --detach b32965525da5f982599af9794954c616ddeb34ff
python3 -m venv .agent-drafts/streammembench-py312
.agent-drafts/streammembench-py312/bin/python3 -m pip install PyYAML==6.0.3
cd .agent-drafts/upstream/StreamMemBench
env -i PATH=/usr/bin:/bin PYTHONPATH=src ../../streammembench-py312/bin/python3 \
  -m streammembench.cli eval --system rag_raw --config configs/evaluation/release_sample.yaml \
  --max-items 1 --run-id streammembench-release-wiring-20261018 \
  --output ../../streammembench-release-smoke/rag_raw.jsonl
env -i PATH=/usr/bin:/bin PYTHONPATH=src ../../streammembench-py312/bin/python3 \
  -m streammembench.cli aggregate --results ../../streammembench-release-smoke
```

The mini run used `configs/evaluation/smoke.yaml` without `--max-items`, outputting to `.agent-drafts/streammembench-smoke/`. Raw outputs and diagnostic sidecars remain local; no dataset or raw participant text is committed. Registry source: `docs/experiments/registry.json`, experiment `EXP-STREAMMEMBENCH`.

The native indexer generated and verified all three views locally, including VCS reconciliation and this plan's artifact link. Generated snapshots remain in the ignored preview directory to keep unrelated historical/worktree refreshes out of this tracking slice. Rebuild from the repository root:

```sh
python3 scripts/experiment_index.py --status .agent-drafts/streammembench-index/STATUS.md \
  --index-json .agent-drafts/streammembench-index/index.json \
  --scoreboard .agent-drafts/streammembench-index/scoreboard.html
```
