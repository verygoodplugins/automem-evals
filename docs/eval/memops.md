# MemOps — lifecycle memory operations: design and offline scaffold

Track: [#108](https://github.com/verygoodplugins/automem-evals/issues/108) (its body is the acceptance checklist). Candidate: `opportunity:automem-graph-rag-research-scout`. Related, not duplicated: [#50](https://github.com/verygoodplugins/automem-evals/issues/50) StateMemBench, [#51](https://github.com/verygoodplugins/automem-evals/issues/51) MemTrace, [#57](https://github.com/verygoodplugins/automem-evals/issues/57) A-TMA, [#22](https://github.com/verygoodplugins/automem-evals/issues/22) FAMA, [#31](https://github.com/verygoodplugins/automem-evals/issues/31) ForgetEval, [#53](https://github.com/verygoodplugins/automem-evals/issues/53) MERIT, [#62](https://github.com/verygoodplugins/automem-evals/issues/62) Veracium, PR [#61](https://github.com/verygoodplugins/automem-evals/pull/61) EvalMem (see [Relation to existing trackers](#relation-to-existing-trackers)).

**Desk review plus offline scaffold. Nothing was run against AutoMem, no model credits were spent, and no AutoMem score exists.** Status is `not_scored` and `paper_comparable` is `false`. Every accuracy figure below is **paper-reported** (checked against the v1 PDF) and is a baseline, never an AutoMem result. Checked 2026-11-18.

## Source and availability

| Artifact | Pin / availability |
| --- | --- |
| [Paper](https://arxiv.org/abs/2607.12893) | "MemOps: Benchmarking Lifecycle Memory Operations in Long-Horizon Conversations", cs.AI, Hao et al., v1 2026-07-14 15:33:44 UTC. v1 PDF sha256 `2add252b60c9bf5a87a631f39cb0fe28c424ad7910bd267d64b002db94ead39b`. arXiv non-exclusive distribution license (paper only). |
| [Code + data `MemTensor/MemOps`](https://github.com/MemTensor/MemOps/tree/312af65e2c7b6d1b70f062ffa8b4cde32aaf6f35) | **Pinned at commit `312af65e2c7b6d1b70f062ffa8b4cde32aaf6f35`** (2026-07-24 13:23 UTC, "update"). Default branch `main`, no tags or releases, 14 stars, not archived. Linked from the paper's HTML. Research-preview README. |
| Data location | **Shipped in the repo** under `generated_result/` (tree `afd79cb5770c2ab76196c02e115718995b07fdac`); no Hugging Face dataset exists under `MemTensor` or by search. Evidence set `2-evidence_conversation/` (tree `4db48ff6…`): 403 files, 23,152,720 bytes. Injected set `4-inject_evidence_with_distractors/` (tree `f351903f…`): 403 files, 177,888,197 bytes. |
| Pin digest | sha256 over sorted `<name>\0<sha256(file bytes)>\n` lines of the `*.json` files: evidence `2b819b54d66a71d8070f1b953016e2274dd5584e5b1a1b1ba89732bc3727b70e`, injected `bccd8c449a6892355d07b978d912531b23c30a5e33dd0f07e509f154e16061ab`. `runners/memops/adapter.py` `verify_pin` **fails closed** on the evidence digest. |

## License status

- Code and the shipped data: **MIT** (`LICENSE` blob `8d3647227143ff3ff58677f7d026c0326fec58f7`, "Copyright (c) 2026 MemTensor"; the README's license section says "MemOps is released under the MIT License"). There is no separate data license.
- The carrier sessions come from UltraChat (the Hugging Face card says MIT). The data was generated with external LLMs; those models' output terms are unverified.
- **Rules for this repo:** MIT permits vendoring, but the injected set is 178 MB, so commit nothing upstream: fetch by commit, verify the digest, keep the checkout in an ignored directory, and write adapter code from the documented schema without copying upstream method bodies.

## What MemOps measures

Each topic yields one evidence conversation per operation type (Remember, Forget, Update, Reflect, TrajectoryOps), three segments of eight alternating turns. The paper's Table 2 reports 727 generated and 403 retained. Every question is asked in **two settings**: *adjacent* (clean evidence, mean 2,557 tokens) and *long-context* (evidence segments dispersed in 50 UltraChat sessions plus near-miss distractors, mean 60,821, max 68,309).

Verified at the pin (these match the paper's counts):

| Quantity | Value |
| --- | --- |
| Evidence conversations / segments / turns | 403 / 1,209 / 9,672 (4,837 user turns) |
| Probe instances | 4,012 = 2,006 per setting (OperationTrace 806, TargetBinding 806, StateTransition 788, CandidateDisambiguation 642, OperationApplication 806, StateTrajectory 164, both settings together) |
| Evidence files by type | Reflect 96, TrajectoryOps 82, Forget 80, Update 77, Remember 68 |
| Gold operations | 2,558: remember 1,864, update 488, reflect 124, forget 82; confirmed 2,296, tentative 260, retracted 2; 647 carry `chain_id`/`chain_step` |
| Difficulty knobs enabled | `multi_target`, `multi_hop`, `negative_seed`, `adversarial_injection` in all 403; `recency_trap` 255; `update_chain` 159 |
| Injected files | 50 sessions each; 20,150 sessions, 217,112 turns, **108,557 user turns** in total |

**Gold trace schema** (evidence file): `target_fact`, `operation_type`, `difficulty_knobs`, `conversations[].dialogue[]`, `operations[]` and `answer[]`; `state_checkpoints[]` appears in the 82 TrajectoryOps files. An operation has `operation_id`, `type`, `validity`, `trigger_span` (`segment_index`, 1-based `turn_index`, `quote`), `target` (`target_id`, `target_name`), `old_value`, `new_value`, `evidence_spans[]` and optional `chain_id`/`chain_step`. A probe has `question_pair_id`, `evaluation_setting`, `evaluation_type`, `question`, `expected_answer`, `gold_memory_state`, `judge_rubric` (`must_include`, `must_not_include`, `harmful_extra`, ...), `diagnostic_checks` (`leakage`, `over_forget`, `stale_value`, `reflection_precision`, `reflection_recall`, `trajectory_order`, `final_state`, `intermediate_state`, `trajectory_provenance`; mostly prose rubrics), `gold_provenance`, plus `candidate_options` (642) and `gold_reasoning_chain`. Injected files keep the questions and add `injection_metadata`; **`conversation_index` is 1-based and the evidence messages sit at `dialogue[insertion_index : insertion_index + evidence_message_count]`** (text-verified for all 403 files by `locate_evidence`). All 403 files pass `validate_record`, and every trigger quote is verbatim in its user turn.

## Paper-reported baselines (not AutoMem scores)

Accuracy, paper Tables 3 to 5 (v1 PDF); the operation diagnostics use a GPT-4o-based judge. Claude and Qwen cells read adjacent / long-context; the RAG row reads session-level / turn-level; Mem0 is a single setting:

| Method | Overall | Remember | Forget | Update | Reflect | TrajectoryOps |
| --- | --- | --- | --- | --- | --- | --- |
| Claude-Sonnet-4.5 | 0.916 / 0.790 | 0.946 / 0.811 | 0.875 / 0.735 | 0.916 / 0.838 | 0.898 / 0.752 | 0.949 / 0.829 |
| Qwen3.6-27b | 0.914 / 0.790 | 0.936 / 0.826 | 0.913 / 0.768 | 0.929 / 0.847 | 0.869 / 0.758 | 0.934 / 0.768 |
| BM25 RAG (GPT-4.1-mini), session / turn level | 0.845 / 0.618 | 0.897 / 0.757 | 0.807 / 0.650 | 0.821 / 0.519 | 0.900 / 0.683 | 0.785 / 0.444 |
| Mem0 | 0.543 | 0.645 | 0.580 | 0.510 | 0.550 | 0.424 |

Best per probe, adjacent / long-context: OperationTrace 0.883 (Qwen3.6-27b) / 0.670 (GLM-4.6); TargetBinding 0.940 (Claude) / 0.886 (GLM); StateTransition 0.931 (Qwen) / 0.865 (DeepSeek-V4-Flash); CandidateDisambiguation 0.988 (Claude) / 0.984 (GPT-4o); OperationApplication 0.891 (Claude) / 0.893 (Qwen); **StateTrajectory 0.927 (Claude) / 0.598 (Claude)**. Our reading: operation tracing and trajectory recovery fall sharply with distance, while candidate disambiguation barely moves. Table 3 also reports operation F1, provenance, leakage, stale-value rate and reflect precision (Claude adjacent: 0.887, 0.941, 0.230, 0.045, 0.874; lower is better for leakage and stale value; Qwen adjacent leakage is 0.095).

## Relation to existing trackers

| Tracker | What it measures | MemOps adds |
| --- | --- | --- |
| #50 StateMemBench, #22/#23 FAMA, #57 A-TMA | answer uses the operative state; invalid-memory reuse; ghost memory | one outcome each; MemOps traces the **operation that produced the state** across remember/forget/update/reflect |
| #31 ForgetEval | control-plane forget API (supersede, release, purge) | forget is one of four operations, and the probe asks about the **resulting state**, not the API result |
| #51 MemTrace, PR #61 EvalMem | evidence use; encoding/retrieval/generation defect layers | per-operation, per-probe cells with a gold trace instead of defect layers on QA |
| #53 MERIT, #62 Veracium | action value; validity intervals and provenance | different constructs; Veracium as-of sets are the nearest cousin of `StateTrajectory` |

## AutoMem mapping

Verified against automem `1a7ba1a6afe69835f62ad7f6013e33301d1ab83e` (`docs/API.md`, `automem/api/memory.py`) and this repo's adapters (`scripts/benchmarks/memora_fama_adapter.py`, `runners/beam_retrieval_eval.py`, `runners/client_side_expand.py`).

| MemOps operation | Plan steps | AutoMem call |
| --- | --- | --- |
| remember (confirmed) | `store` the trigger user turn | `POST /memory` (`type` Context, `timestamp` = `t_valid` from the synthetic clock, tags `memops:<run>`, `memops:conv:<id>`, `memops:target:<target_id>`) |
| remember / update (tentative) | `store` with `confidence` 0.3 and `memops:validity:tentative`; never becomes current | `POST /memory`; **no** supersession (the `recency_trap` knob) |
| update | `store` new turn, then supersede the target's current memory | `POST /memory`, `PATCH /memory/<old>` `{t_invalid}`, `POST /associate` `INVALIDATED_BY` old to new (the `supersedes_memory_id` sequence the MCP `store_memory` performs) |
| forget | soft: `PATCH {t_invalid}` on every memory bound to the target; hard: `DELETE`. The trigger turn is **not stored** (no retrievable tombstone) | `PATCH /memory/<id>` / `DELETE /memory/<id>` |
| reflect | `store` the reflection `new_value` and link it to its evidence turns | `POST /memory` type `Insight`, `POST /associate` `DERIVED_FROM` (authorable) |
| TrajectoryOps | the steps above in trigger order, keyed by `chain_id` | same; `state_checkpoints` become per-step probes later |
| retracted | skipped (2 ops at the pin) | none |

**Write arms** (`runners/memops/adapter.py`): `raw_turns` (every user turn, no lifecycle calls; the raw-history control), `oracle_lifecycle_soft` (`t_invalid` plus `INVALIDATED_BY`), `oracle_lifecycle_hard` (`DELETE` on forget), `oracle_inplace` (`PATCH content` on update, which loses history). The `oracle_*` arms read the **gold** trace, so they are upper bounds for a lifecycle writer, not what an agent would infer; an inferring arm needs a paid extractor and is out of scope. Plan sizes at the pin, adjacent: `raw_turns` 4,837 stores; soft 2,571 stores, 767 associations, 410 patches; hard the same minus 81 patches plus 81 deletes; in-place 2,244 stores, 438 associations, 410 patches. Long-context adds 103,720 filler stores to every arm. Two forget ops have no bound memory (warnings, not errors).

**Probe reads:** one `GET /recall` per question with `tags=[memops:<run>, memops:conv:<id>]`, `tag_mode=all`, `tag_match=exact`, `limit=10` and `state_mode=history` for OperationTrace, StateTransition and StateTrajectory (they need the before-state) or `current` for the rest. Request parameters never contain `expected_answer`, `judge_rubric` or any gold value (tested). Server-side `expand_relations` is a no-op under tag gating (CLAUDE.md invariant 2); a graph-on arm must use `runners/client_side_expand.py`.

**Design hazards found.** (1) Memory granularity is the user turn, so a soft forget of one target in a multi-fact turn also hides sibling facts: the over-forget diagnostic matters because `multi_target` is on in all 403 files. (2) In 24 cases an operation shares its trigger turn with another operation, so if a forget shares its turn, that turn is stored for the other operation (not checked per file). (3) `oracle_inplace` cannot answer `StateTransition` before-state probes by construction, which is the point of the arm.

## Per-operation probe reporting

A cell is operation type x probe x setting x arm x variant, holding `n`, `support_labeled/hits/rate` and `leak_labeled/leaks/rate`. Support is "every `must_include` string appears in the recalled text" and leak is "any `must_not_include` string appears" (case-insensitive substring, a **lower bound**; paraphrases are not credited). A question with no label is **unknown, never zero**. The `diagnostic_checks` that need judgement (leakage, over_forget, trajectory order, reflection precision/recall) are `judge_required` and stay `not_scored` offline. **Final-answer accuracy is a separate field** (`final_answer_accuracy`, null) that needs an answerer and a judge; probe cells never carry it. `aggregate` refuses to score unless every planned question has a result.

## Cold vs matured

Per [maturation.md](maturation.md), `cold` (ingest, then recall) and `matured` (enrichment drained, consolidation and invalidation passes with decay off, narrative `reference_time` after the last segment) are **separate columns**, never merged. MemOps has no dates, so the narrative clock is synthetic (one day per conversation, one minute per turn, never wall-clock) and must be disclosed. Run matured on `raw_turns` first: it shows whether AutoMem's own invalidation recovers Update and Forget without the oracle writer; on the `oracle_*` arms the delta is confounded.

## Scaffold and verification

`runners/memops/adapter.py` is stdlib only and offline: it validates records, builds ingest and recall plans, classifies and aggregates results, and emits a `not_scored` report. The CLI (`python3 runners/memops/adapter.py [--memops-dir DIR]`) has no recall transport. `runners/test_memops.py` has 20 tests; `MEMOPS_DIR=<pinned checkout>` enables the test that validates all 403 records and locates evidence in all 403 injected files.

## Gates and cost

- **Spend:** none approved. `docs/eval/paid-budget.md` supports `gpt-5-mini`, `gpt-5.4-mini-2026-03-17`, `voyage-4` and `text-embedding-3-small`. The paper's judge (GPT-4o) and the README's default models are not routable, so a run needs a non-comparable judge column or verified proxy prices first.
- **Embeddings:** 4,837 stores for adjacent, 108,557 for long-context across all files, so long-context needs its own cap.
- **Smoke proposal (owner decision):** topic `A02` (one file per operation type): 25 questions per setting, 60 adjacent and 1,328 long-context writes for `raw_turns`. Adjacent first, cold then matured, wiring only (`subset: smoke`).

## Follow-up notes

- **DyadMem** ([arXiv:2610.03020](https://arxiv.org/abs/2610.03020), 2026-10-02, CC BY 4.0): user-conditioned relational memory, 6 categories, about 3,065 episodes, 50,961 sessions, 61,210 QA, session-level capture/update annotations, Gold-Memory vs Full-Pipeline QA; reports low capture recall, incomplete recall and unsafe deletion. **Artifact-blocked, no tracker filed.** The arXiv page links no code or data. `RenaissanceT/DyadMem` (MIT, `a5f4fa96b3f0a1d361a74565eb7793ed9b6a7cf6`) holds only a paper-page template and SVG figures with unconfirmed authorship; `ZombieProject2021/dyadmem` (no license, a 48 MB `.rar`) has unverified provenance and was not downloaded. Revisit when the authors link artifacts; its capture/update/deletion annotations should reuse the MemOps probe cells.
- **DolphinBench** ([arXiv:2609.24971](https://arxiv.org/abs/2609.24971)): already tracked in [#45](https://github.com/verygoodplugins/automem-evals/issues/45), #46 and #69, so no new note. Its accuracy, total-cost and median-latency triple is the frame if MemOps later reports a cost-aware Pareto view.
