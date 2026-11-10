# EvoMemBench — self-evolving agent memory: adapter feasibility and CrossEp-Know smoke plan

Track: [#90](https://github.com/verygoodplugins/automem-evals/issues/90); its body is the [acceptance checklist](#acceptance-checklist-tracking-issue-body) below. Candidate: `opportunity:automem-graph-rag-research-scout`. Related: [#67](https://github.com/verygoodplugins/automem-evals/issues/67) (StreamMemBench, same `INVALIDATED_BY` + `t_invalid` convention), [#89](https://github.com/verygoodplugins/automem-evals/issues/89) (MemTools, same desk-review format), [MEME](meme.md) (PR #85; spend-guard constraints), [#28](https://github.com/verygoodplugins/automem-evals/issues/28) (scout note).

**Desk review only. Nothing was run against AutoMem, no upstream benchmark code was executed, and no model credits were spent.** Every accuracy figure below is either **paper-reported** or **recomputed from files committed in the upstream repo**, and none is an AutoMem score. Checked 2026-11-10.

## Source and availability

| Artifact | Pin / availability |
| --- | --- |
| [Paper](https://arxiv.org/abs/2605.18421) | "EvoMemBench: Benchmarking Agent Memory from a Self-Evolving Perspective", cs.CL, 10 authors (HKUST-GZ lead). v1 2026-05-18, v2 2026-06-15, **v3 2026-10-30 08:21 UTC**; arXiv comment "Accepted by NeurIPS 2026" (Evaluations and Datasets track per the PDF footer). v3 PDF sha256 `2c611d1316bc2ad7ca8583c81785e5f0631f16241fb01df527af8ac021f8cd44`. |
| [Code + data `DSAIL-Memory/EvoMemBench`](https://github.com/DSAIL-Memory/EvoMemBench/tree/3efc221fd8d5f4de7c2dc2022357e600d26325c7) | **Pinned at commit `3efc221fd8d5f4de7c2dc2022357e600d26325c7`** (2026-11-03 12:55 UTC, "Update README with dataset information"; root tree `6fdbd8c1ae70c3e260ea6f7be6fadc0a8891cc71`). The request called the commit sha a tree sha. `main` is the default branch, created 2026-05-18, 19 stars, not archived. Pinned layout: `Cross-Episode-Execution/` (418 files), `Cross-Episode-Knowledge/` (54, 85 MB), `In-Episode-Execution/` (286), `In-Episode-Knowledge/` (208, 43 MB), `EvoMemBench-Memory-Systems/` (2,935 files, 67 MB), `README.md`, `assets/`. |
| [HF mirror `littlewyy/EvoMemBench`](https://huggingface.co/datasets/littlewyy/EvoMemBench/tree/4a70996984638d396d9e942ee6f60d55b43be00d) | Revision `4a70996984638d396d9e942ee6f60d55b43be00d` (2026-11-03), ungated, nine parquet configs covering the six datasets, tagged `arxiv:2605.18421`. The README itself recommends the original repo format over this converted copy. **The dataset card declares no license.** Not used below. |
| CrossEp-Know data file | `Cross-Episode-Knowledge/CROSSEP-KNOW/CL-bench_context_ge5.jsonl`: 21,520,169 bytes, SHA-256 `f4652ddcf954dd33653f91c9b40ed6138617b92e0f80d470cd1c92bb50890ce9`, git blob `9c339865f658b056bc5a10862e7e9fe9e64e7e31` (equals the pinned tree entry; downloaded and re-hashed locally into an ignored scratch directory). |

Duplicate check (2026-11-10): the 89 issues and PRs in this repository (all states), 153 comments and the file patches of all 21 open PRs contain no tracker for EvoMemBench, `2605.18421` or `DSAIL-Memory`. The only mention is the [#28 scout comment](https://github.com/verygoodplugins/automem-evals/issues/28#issuecomment-6247053710) (2026-10-18), which lists EvoMemBench, StreamMemBench and MemTools as "un-tracked, low-priority (hold until backlog shrinks)". StreamMemBench ([#67](https://github.com/verygoodplugins/automem-evals/issues/67)) and MemTools ([#89](https://github.com/verygoodplugins/automem-evals/issues/89)) have since been tracked; EvoMemBench is the last one. That comment is a backlog note, not a tracker.

## License status: no grant, do not vendor

- GitHub reports `license: null`. There is **no root `LICENSE`, `COPYING` or `NOTICE`**, the README has no license section, and the HF dataset card declares none. Treat the benchmark code and the bundled data as **all rights reserved** until the authors publish a license text.
- The vendored systems under `EvoMemBench-Memory-Systems/` carry their own files: A-mem MIT; MemOS, MemoBrain, MemoryOS and mem0 Apache-2.0; `memagent/` has **no LICENSE file**. Those licenses do not extend to the benchmark's own task code.
- Upstream sources, as GitHub reports them: MemoryAgentBench MIT, BFCL (gorilla) Apache-2.0, MemEvolve Apache-2.0, AgentGym MIT. [CL-bench](https://github.com/Tencent-Hunyuan/CL-bench) states Apache-2.0 for its **code** only and GitHub reports `NOASSERTION`; the HF dataset `tencent/CL-bench` is tagged `license:other`. CrossEp-Know's data is derived from CL-bench, so its terms are unresolved (we did not read the HF card's terms).
- **Rules for this repo:** commit no upstream code or data (not even the 884-row subset), fetch at run time by commit and verify the SHA-256 above, write adapter code from the documented two-method interface without copying upstream method bodies, and import the upstream `Memory` base class only from a user-supplied pinned checkout in an ignored directory. Asking the authors to add a license is an owner decision (listed in the checklist); nothing was sent upstream.

## What EvoMemBench measures

Two axes (memory scope: in-episode vs cross-episode; memory content: knowledge vs execution) give four settings and six datasets (paper Table 2, upstream README):

| Setting | Dataset (dir) | Source | Samples | Metric |
| --- | --- | --- | --- | --- |
| In-episode knowledge | InEp-Know (`In-Episode-Knowledge/INEP-KNOW`) | MemoryAgentBench Accurate Retrieval (EventQA 500, LongMemEval-S* 300, RULER qa1 100, qa2 100) and Conflict Resolution (FactConsolidation single-hop 100, multi-hop 100), all at 262K | 1,200 QA | Accuracy (`eventqa_recall`, LongMemEval judge, `substring_exact_match`) |
| In-episode execution | InEp-Exec (`In-Episode-Execution/INEP-EXEC`) | BFCL multi-turn long-context, rewritten with implicit references (GPT-5-mini-assisted, manually checked) | 200 (4 envs x 50), budgets 16K/32K/64K/128K | Success rate, progress score |
| Cross-episode knowledge | **CrossEp-Know** (`Cross-Episode-Knowledge/CROSSEP-KNOW`) | CL-bench contexts with at least 5 tasks | **884 episodes, 120 contexts** | All-or-nothing rubric accuracy |
| Cross-episode execution | CrossEp-Tool, CrossEp-Web, CrossEp-Emb (`Cross-Episode-Execution/*`) | BFCL multi-turn base (200); xbench-DeepSearch 100 + WebWalkerQA 170; ALFWorld six task types (200) | 670 | Success rate |

Protocol (paper §5.1): memory-free agents are Gemini-3-Flash, GPT-5-mini and DeepSeek-V3.2; every memory method uses **DeepSeek-V3.2** as backbone, DashScope `text-embedding-v4` unless the method needs its own, top-k **10** for knowledge tasks and 3 for execution tasks. In-episode memory is initialized per episode, updated online and cleared; cross-episode memory is updated after each episode and reset when the context (or environment group) changes. Procedural methods are excluded from InEp-Know and short-term methods from the cross-episode suites. The paper text names no judge model, run count, seed or variance; the pinned `eval.py` defaults to judge `gpt-5.1` and sets no temperature. We infer the tables are single runs.

## The 15 methods (paper Appendix A.3)

| Family | Methods | Pinned code in `CROSSEP-KNOW` registry |
| --- | --- | --- |
| Retrieval-augmented | BM25, Qwen3-Emb-4B, GraphRAG | `bm25`, `qwen3_embedding_4b`, `graphrag` |
| Short-term | MemAgent, MemoBrain | none (InEp suites only; `EvoMemBench-Memory-Systems/memagent`, `MemoBrain` need a local vLLM server) |
| General long-term | Mem0, A-MEM, MemOS, MemoryOS | `mem0`, `a_mem`, `memos`, `memoryos` |
| Procedural long-term | AWM, SkillWeaver, AgentKB, ACE, ReasoningBank | `agent_workflow`, `skillweaver`, `agent_kb`, `ace`, `reasoning_bank` |
| Meta-evolution | MemEvolve | `lightweight` (its docstring says "adapted from LightweightMemoryProvider (EvolveLab)"; mapping it to the MemEvolve row is our inference) |

Applicable memory methods per table: InEp-Know 9 (Table 3), InEp-Exec 15 (Table 4), CrossEp-Know 13 (Table 5), CrossEp execution 13 (Table 6). By the paper's own descriptions, none of the 15 models validity intervals or supersession edges as a first-class concept (Mem0's ADD/UPDATE/DELETE/NOOP is the nearest; our reading), and AutoMem is not one of them.

## Paper-reported results (not AutoMem scores)

CrossEp-Know accuracy (%), Table 5 "Overall" columns by difficulty tier. Tiers are tertiles of contexts by the DeepSeek-V3.2 no-memory score, assigned per category:

| Method | Easy | Medium | Hard | Method | Easy | Medium | Hard |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Gemini-3-Flash | 37.3 | 13.0 | 7.8 | Mem0 | 44.6 | 11.7 | 3.8 |
| GPT-5-mini | 60.8 | 21.6 | 14.4 | A-MEM | 43.8 | 10.0 | 6.7 |
| DeepSeek-V3.2 (no memory) | 52.1 | 12.6 | 0.0 | MemOS | 46.8 | 14.8 | 6.8 |
| BM25 | 47.2 | 13.8 | 10.1 | MemoryOS | 44.2 | 11.0 | 9.0 |
| Qwen3-Emb-4B | 50.0 | 13.7 | 7.9 | AWM | 46.0 | 12.5 | 4.8 |
| GraphRAG | 48.0 | 13.7 | 7.7 | SkillWeaver | 48.4 | 11.3 | 5.6 |
| ACE | 44.8 | 16.5 | 13.0 | AgentKB | 45.6 | 11.3 | 3.6 |
| ReasoningBank | 42.7 | 15.7 | 6.1 | MemEvolve | 46.0 | 12.0 | 7.4 |

InEp-Know FactConsolidation accuracy (%), Table 3 (multi-hop / single-hop), the only suite where supersession is the task: Gemini-3-Flash 58 / 96, GPT-5-mini 24 / 77, DeepSeek-V3.2 10 / 65, BM25 7 / 54, Qwen3-Emb-4B 4 / 30, GraphRAG 4 / 18, MemAgent 3 / 19, MemoBrain 1 / 20, Mem0 7 / 49, A-MEM 5 / 35, MemOS 3 / 35, MemoryOS 2 / 30.

The paper's headline findings: long-context baselines stay competitive; memory helps on hard tasks and can hurt easy ones (DeepSeek-V3.2 52.1 vs best memory 50.0 on Easy); existing methods retain better than they revise; no memory form wins everywhere.

**Caveats we found (ours, not the authors').**
- The tier definition makes the DeepSeek-V3.2 Hard score **0.0 by construction**, so Hard-tier gains for any memory method are partly regression to the mean (our inference).
- The committed no-memory output does not reproduce the paper's baseline row. Recomputed from `outputs/context_nomemory/..._graded.jsonl` (884 rows, `idx` set equals the data's `task_id` set, SHA-256 `7217429cdb837c43f6157241ce7578dd0eb892398141c26d4cecef7475ed531d`) with the committed `difficulty_tiers.csv` (SHA-256 `3e8e46ce505cb4decdce966a4bdddec485c641f9e1a7e0843beb3abddf49b659`): **211 / 884 = 23.9% overall; Easy 163/295 = 55.3, Medium 40/302 = 13.2, Hard 8/287 = 2.8** over 42 / 39 / 39 contexts, against the paper's 52.1 / 12.6 / 0.0. The CSV's `baseline_sample` differs from the recomputed per-context mean in **49 of 120 contexts**, so the committed file is a different run from the one that defined the tiers. Rerun noise at this scale is itself informative: do not read a single-run difference of a few points as a method effect.
- Scoring is all-or-nothing over a median of 20 rubric strings per episode (4 to 114; 21,142 in total), so a partially right answer scores 0.

## What AutoMem can map to

AutoMem features used below are verified in this repo: `/memory/batch` maps `timestamp` to `t_valid` (`runners/beam_retrieval_eval.py:659`); `PATCH /memory/<id>` with `t_invalid` and `POST /associate` with `INVALIDATED_BY` / `EVOLVED_INTO`, old to new, plus `current_only` recall (`scripts/benchmarks/memora_fama_adapter.py`); inline `results[].relations[]` for client-side expansion, since server-side `expand_relations` is a no-op under tag gating (`runners/client_side_expand.py`, CLAUDE.md invariant 2).

| Setting | Recall / graph | `t_valid` / `t_invalid` | `INVALIDATED_BY` / `EVOLVED_INTO` | Verdict |
| --- | --- | --- | --- | --- |
| In-episode knowledge | Direct for the 1,000 Accurate Retrieval questions (LongMemEval-style claims stay in `automem`; label any run experimental per `docs/REPO_BOUNDARY.md`) | **Partial.** FactConsolidation facts carry serial numbers and the pinned prompt says the newer fact has the larger number, so the serial maps to `t_valid` order. Deciding which older fact a new one voids has no label in the context, and the metadata fields `previous_events` and `keypoints` are label-adjacent until inspected, so exclude them | **Partial.** Only if the adapter infers the (subject, relation) slot per fact; multi-hop needs chain following | Best semantic fit for AutoMem's differentiator and the largest paper-reported headroom (multi-hop 1 to 7% for every memory method vs 58 for Gemini-3-Flash). Heavy: the 262K contexts are about 1.1M characters each and need fact-level extraction. Separate follow-up, not first |
| In-episode execution | Partial (store tool outputs, recall at later turns) | Only if the adapter models environment state changes; no labels, unverified | None natural | Low to medium. Needs BFCL function-calling infrastructure; defer |
| **Cross-episode knowledge** | **Direct.** One tag per `context_id`, `tag_match=exact`, `retrieve` to `/recall` (limit 10), `extract` to `POST /memory` | **Not exercised.** The data has no timestamps or revision events (metadata is `task_id`, `context_id`, `context_category`, `sub_category`). A synthetic order clock is needed and must be disclosed | **Not exercised.** `EVOLVED_INTO` is usable only as an adapter-chosen consolidation arm, which the benchmark cannot credit by design | **First target for wiring.** Smallest interface, text only, local HTTP, no simulator. It tests store/recall utility, not supersession |
| Cross-episode execution | Partial (retrieve past trajectories; the paper finds retrieval best on tool use, average rank 5.43) | None | None | Heavy environments: BFCL executables, live web with `SERPER_API_KEY`, ALFWorld `agentenv` server plus `alfworld-download`. Defer |

Why CrossEp-Know is a weak memory test (verified in the pinned data): in **120 of 120 contexts the system message, which holds the knowledge, is identical across all of the context's episodes**. Memory therefore cannot supply missing knowledge; it can only carry earlier attempts at the same context. Upstream `extract` receives the episode's messages plus the model's own output, **with no correctness signal** (CrossEp-Emb's `update`, by contrast, takes an optional `reward`), so stored content is unverified self-output. Expect small effects: in the paper's Table 5 all 13 memory methods sit below the no-memory row on Easy (-2.1 to -9.4 points) and within -2.6 to +3.9 points of it on Medium.

## Loader schema (CrossEp-Know, verified at the pin)

Input, one JSON object per line, 884 lines, 120 contexts contiguous in file order (5 to 12 episodes each; 62 contexts have 7):

```json
{"messages": [{"role": "system|user|assistant", "content": "..."}],
 "metadata": {"task_id": "uuid", "context_id": "uuid", "context_category": "...", "sub_category": "..."},
 "rubrics": ["Does the agent ... Fail if ...", "..."]}
```

859 episodes are `[system, user]`; 25 (in 6 contexts) alternate user/assistant up to 12 messages (the pinned mem0 backend's docstring treats the earlier assistant turns as ground-truth demonstrations). The query upstream passes to memory is the **last user message** (median 7,781 characters, p90 10,991, p99 19,559, max 167,209; 2 episodes above 32K). Categories: Procedural Task Execution 306, Domain Knowledge Reasoning 294, Rule System Application 257, Empirical Discovery & Simulation 27.

Run output adds `idx` (= `task_id`), `model_output`, `memory_type`, `memory_retrieved`, and `stats` (`latency.{retrieve_s,inference_s,extract_s,total_s}`, `tokens.{inference,extract_llm,retrieve_embed,extract_embed}`); `eval.py` adds `score` (0 or 1), `grading_rationale` and `requirement_status`. Other suites, as far as inspected: InEp-Know rows are MemoryAgentBench `{context, questions, answers, metadata{source, question_ids, previous_events, keypoints, ...}}` (the `factconsolidation_*` context opens "Here is a list of facts:\n0. ..."); BFCL and ALFWorld formats were not inspected.

## How an adapter plugs in

**`EvoMemBench-Memory-Systems/` is not a plugin registry.** It holds vendored editable copies of six memory packages (`mem0`, `A-mem`, `MemOS`, `MemoryOS`, `MemoBrain`, `memagent`) that the task scripts `pip install -e`. The README points to an `EvoMemBench-Memory-Systems/README.md` that does not exist at the pin. The adapters themselves live **inside each task directory**, each with its own base class, so there is no single cross-suite contract (the paper says every method is wrapped with `utilize` and `update`):

| Suite | Base class and hooks at the pin | Registration |
| --- | --- | --- |
| CrossEp-Know | `cl_bench_memory/base.py` `Memory.retrieve(query) -> (text, stats)`, `Memory.extract(content, **kwargs) -> stats` (kwargs: `task_id`, `query`, `context_category`, `sub_category`) | `cl_bench_memory/registry.py` `build_memory(memory_type, **kwargs)`, an `if` chain |
| CrossEp-Tool | `bfcl_eval/memory/base.py` `Memory.utilize(system_prompt) -> str`, `update(trajectory)`, classmethod `load_from_disk` | `bfcl_eval/memory/factory.py` |
| CrossEp-Emb | `scripts/memory/base.py` `BaseMemory.inject(conversation) -> (conversation, stats)`, `update(conversation, data_idx, reward)`, `load_from_disk` | `create_memory` in the same file |
| InEp-Know | MemoryAgentBench `agent.py` backend routing plus YAML agent configs | not inspected in detail |

For CrossEp-Know the driver builds one backend **per context** with `memory_dir`, `top_k`, `client`, `embed_client`, `extract_model`; calls `retrieve` once per episode with the last user message; appends the returned text to the system message; then calls `extract` with the formatted trajectory (system context, user turns, assistant turns, then the model output). Three non-obvious requirements: the driver reads `len(memory.memory_bank)` after each context, so the backend must expose a `memory_bank` list that the ABC does not declare; it builds an embedding client for the chosen `--embed-provider` before the backend exists (DashScope keys are required for the default, so an AutoMem run needs a provider path that does not, to be verified); and the upstream mem0 backend swallows retrieval errors and returns empty text, so a broken endpoint would silently look like "no memory". An AutoMem adapter must count and report such errors.

Proposed mapping (nothing built):

| Hook | AutoMem mapping |
| --- | --- |
| construction | Loopback endpoint only (reuse the `is_local_endpoint` guard in `runners/beam_retrieval_eval.py`); tags `evomembench:<run>:<context_id>`; no `memory_dir` needed because AutoMem is a network service, so it does not belong under `EvoMemBench-Memory-Systems/` |
| `extract` | Arm A0: verbatim trajectory chunks via `POST /memory` (no LLM, analogue of the BM25/embedding arms). Arm A1: distilled lessons by a disclosed extraction LLM (analogue of Mem0/ReasoningBank). Never read `rubrics`. `t_valid` from a deterministic synthetic clock keyed to episode order, never wall-clock |
| `retrieve` | Exactly one `GET /recall` per episode, `limit` = top-k (default 10), `tag_match=exact`. The last user message can reach 167K characters and `/recall` is GET-only, so the adapter must define, record and test a query truncation rule (the server's limit is unmeasured). Return text with an explicit prefix such as "[Memory from previous episodes]" |
| arm A2 (optional) | `EVOLVED_INTO` from an older lesson to a refined one, labelled as an adapter-chosen consolidation arm |
| registration | A launcher in this repo patches `build_memory` (and the name `infer_context_memory` bound at import) in process, so the pinned checkout stays unmodified. Verify this works before relying on it |
| `reset` / cleanup | Delete only the UUIDs this run created |

## Proposed smoke subset

Three contexts, **17 episodes, 188,809 message characters**, chosen by a deterministic rule: the smallest context by total message characters in each difficulty tier. The driver's `--max-samples` takes the first N rows in file order, so the subset must be a derived JSONL passed through `--input`, written to an ignored directory.

| Tier | `context_id` | Episodes | Category | CSV `baseline_sample` | Committed no-memory score |
| --- | --- | --- | --- | --- | --- |
| Easy | `20504455-fdc6-4cda-bf7c-25cfc5508fdc` | 5 | Rule System Application / Technical Standards | 1.0000 | 3/5 |
| Medium | `92e91ec2-6de2-4143-a5c8-6ba9b05c74d0` | 6 | Procedural Task Execution / Workflow Orchestration | 0.1667 | 0/6 |
| Hard | `fe9e271c-45c7-4c74-baf8-a1d93ad41a54` | 6 | Rule System Application / Game Mechanics | 0.0000 | 0/6 |

The last column (3/17 in total) is read from the committed upstream baseline file, not run by us. At n = 17 the smoke verifies **wiring only**; it supports no accuracy claim about AutoMem.

## Gates and cost

- **G0 wiring (free, no model calls):** stub-transport unit tests for the adapter (see the checklist).
- **G1 spend guard:** `scripts/benchmarks/paid_budget_proxy.py` supports only `gpt-5-mini`, `gpt-5.4-mini-2026-03-17`, `voyage-4` and `text-embedding-3-small` ([paid-budget.md](paid-budget.md)). The paper's DeepSeek-V3.2 backbone, DashScope `text-embedding-v4` and the code's default `gpt-5.1` judge are not routable, and unsupported calls halt the campaign. Run proxy-supported models and publish a **non-comparable** column, or extend the proxy with verified prices first. Whether the upstream request fields in `api_client.call_openai_api` pass the proxy's admission checks is unchecked.
- **G2 cap:** no spend is approved and no AutoMem cost estimate is given. The smoke's size is 17 answerer calls, 17 judge calls and, for arm A1 only, extraction calls (at least one per episode). The frozen AutoMem server's own embedding calls must also go through the proxy's Voyage lane, as in paid-budget.md.

## Acceptance checklist (tracking issue body)

Title: `track: EvoMemBench self-evolving memory eval, adapter feasibility and CrossEp-Know smoke (arXiv:2605.18421, NeurIPS 2026 E&D)`

- [x] Dedupe, pin and desk review (this document): no tracker existed; commit `3efc221f…`, license **no grant**.
- [ ] Owner decision: ask the authors to add a license to `DSAIL-Memory/EvoMemBench` (and clarify CL-bench data terms for the derived subset), or proceed under the no-vendor rules.
- [ ] `runners/evomembench/` fetch step: download the pinned data file into an ignored directory and **fail closed** unless SHA-256 is `f4652ddc…0ce9` and git blob is `9c339865…`; commit no upstream code or data.
- [ ] Overlay backend `retrieve`/`extract` per the pinned `cl_bench_memory/base.py`, plus a `memory_bank` list; loopback-only endpoint; per-context tag with `tag_match=exact`; deletes only its own UUIDs; counts and reports HTTP/protocol errors instead of returning empty memory.
- [ ] Launcher registers the backend without editing the pinned checkout.
- [ ] Unit tests on a stub transport: one `/recall` per episode with `limit` = top-k; recorded query truncation rule; `rubrics` never read; no cross-context leakage; monotonic synthetic `t_valid`, no wall-clock; cleanup removes only own IDs.
- [ ] Smoke on the 3-context / 17-episode subset above, through the **unmodified** upstream `infer_context_memory.py` and `eval.py`, against a local AutoMem endpoint (record the `automem` commit and recall config): no-memory control and arm A0.
- [ ] Result JSON carries per-tier and per-category `correct`/`n`, answerer, judge, embedding model, arm, AutoMem commit and config, upstream pin, query-truncation count, HTTP error count, empty-retrieval count, memory entries per context, token and call counts, `subset: smoke`, `paper_comparable: false`, status `wiring_only`.
- [ ] No spend before an owner-approved cap, and only through the budget proxy with supported models.
- [ ] Publish nothing as an AutoMem score before a full 884-episode run; paper rows stay labelled paper-reported.
- [ ] Decision after the smoke: scale to 884 episodes (arms A0, A1, then A2), and open a separate issue for an InEp-Know FactConsolidation adapter, the only place the benchmark can credit `t_invalid` and `INVALIDATED_BY`.
- [ ] Out of scope: CrossEp-Tool, CrossEp-Web, CrossEp-Emb and InEp-Exec (heavy environments), any change to `automem`'s official benchmark flow.

Scripts used for the numbers above are not committed (they read data we may not redistribute); the method is: download by pinned commit, check SHA-256, then count rows, contexts, messages and rubrics, and join the committed graded file to `difficulty_tiers.csv` by `context_id`.
