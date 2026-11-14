# MemDev-Bench — memory applicability and process preservation for code agents

Status: **spec only, artifact-blocked. No adapter, no paid run, no AutoMem
score.** Written 2026-10-30. Exploratory and internal; official benchmark claims
stay in `automem` ([REPO_BOUNDARY](../REPO_BOUNDARY.md)).

Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.

## 1. Decision

Track MemDev-Bench ([arXiv:2610.27524v1](https://arxiv.org/abs/2610.27524),
"MemDev-Bench: Does Memory Help Code Agents? Benchmarking Memory Systems over
Real Repository Histories", submitted 2026-10-20) as its own evaluation. It asks
a question no other thread here asks: with **executable** code tasks and history
whose relevance is annotated, does memory help or hurt, and does it change how
many steps the agent needs?

Related, but not the same measurement:

| Thread | What it covers | Why this is separate |
| --- | --- | --- |
| #79 Memory Tax | Raw-history RAG vs AutoMem on LongMemEval-S | Conversational QA, no code execution, no relevance-controlled history. |
| #70 MemDerive | Derived-state adapter plan and cold pilot | Event/query benchmark; no agent loop or patch verification. |
| #51 MemTrace | Evidence-use diagnostic (artifact-blocked) | Diagnoses QA evidence use, not task regressions. |
| #50 StateMemBench | Current vs superseded state (artifact-blocked) | Answer state selection; here staleness is only one hypothesised regression cause. |
| [A-TMA/LTP](atma-ltp.md) | State-view ghost memory | Same lifecycle primitives, different task type. |

Dedup on 2026-10-30: a search of this repository's issues and PRs for `MemDev`
returned 0 results. This is one new file. It does not edit `registry.json` or
the generated dashboard files: #77 and #79 both append to `registry.json` and
regenerate `STATUS.md`, `index.json` and `scoreboard.html`, so a third registry
PR would conflict. Add a parked `EXP-MEMDEV-BENCH` record once those land or G0
clears.

## 2. Release status — blocked on official artifacts

**Decision as of 2026-10-30: do not build a substitute benchmark, adapter or
AutoMem score.**

| Checked source | Finding on 2026-10-30 |
| --- | --- |
| [arXiv record](https://arxiv.org/abs/2610.27524) | v1 only (a v2 URL returns 404). cs.AI, 12 authors, no comments field. Links no code, dataset, Hugging Face or project page. Its license link covers the paper, not benchmark artifacts. |
| [arXiv HTML v1](https://arxiv.org/html/2610.27524v1) and [PDF](https://arxiv.org/pdf/2610.27524v1) (text extracted locally) | No MemDev-Bench repository, data or Hugging Face URL. The Reproducibility Statement points to the method sections and appendices, not to a release. The Ethics Statement says the data comes from public GitHub repositories and that licenses are respected, without naming a benchmark license. The only GitHub links are bibliography entries for third-party tools and memory systems. |
| GitHub repository search (`MemDev-Bench`, `memdev-bench`, `MemDevBench`) | Two hits, both unrelated memristive-device benchmarks (`JK1234567899999/memdevice-bench`, `TannerRobison/MemDevice_Benchmark`). Neither is an author release; do not pin them. |
| Hugging Face dataset search (`memdev`) | Empty result. |
| Web search for the exact title plus `github` | No author repository found. |

### Pin ledger

| Artifact | Revision | License | State |
| --- | --- | --- | --- |
| Paper | arXiv:2610.27524v1 | [arXiv non-exclusive distribution license 1.0](http://arxiv.org/licenses/nonexclusive-distrib/1.0/) (the paper only) | pinned |
| Benchmark data (555 base tasks, 4,869 historical tasks) | none published | none stated | **blocked** |
| Task-construction pipeline, loader, official verifier and scorer | none published | none stated | **blocked** |
| Historical trajectories used by FullTraj | none published | none stated | **blocked** (regenerate only after G0) |
| Underlying repositories (SWE-bench Verified/Pro sources) | per task | per repository; the paper does not list them | unresolved until the data ships |
| Agent harness | Claude Code 2.1.170, Harbor 0.3.0 (paper, Table 6) | not checked | paper configuration only |

Revisit only when the authors publish all of: data, loader schema, historical-task
ordering, official verifier and scorer, an immutable revision and checksum, and a
license. Do not reconstruct the benchmark from the paper's mining/annotation
recipe (Sections 2.1–2.3); that would be a different, unvalidated benchmark.

## 3. Paper claims

Everything in this section is a **paper claim** about Claude Code with
DeepSeek-V4-Flash, not an AutoMem result. AutoMem is not mentioned in the paper
and is not among the five main systems (A-Mem, Mem0, MemOS, Supermemory,
Claude-Mem) or the 29 systems in its Appendix F.

| # | Paper claim | Where |
| --- | --- | --- |
| P1 | 4,869 historical tasks for 555 base tasks, 22 repositories, 4 languages. All experiments use the Verified subset: 344 base tasks, 2,987 historical tasks, 12 Python repositories. | Abstract, §2, §3 |
| P2 | Memory mainly improves within-file localization and editing. On 68 tasks NoMem always fails, F2P rises from 18.10% to 23.15–28.57% while file recall rarely moves (2 of 18 settings above baseline). | §4.2, Table 4 |
| P3 | Regressions offset gains. Improvement Tasks (133): Rescue 9.9–13.2%, Harm 4.8–9.9%. Preservation Tasks (50): averaged over the five systems, Harm exceeds Rescue under Noisy (3.7% vs 3.2%) and Repo history (3.2% vs 2.6%). | §4.1, Tables 2–3 |
| P4 | Unrelated history raises Harm without lowering Rescue (mean Harm 7.1% → 8.0% from Relevant to Noisy on Improvement Tasks). | §4.1 |
| P5 | 115 memory-attributed failures over 76 tasks NoMem always solves. Four non-exclusive modes, counts for Relevant/Noisy/Repo: misapplied transfer 27/30/24 (81), compatibility mismatch 21/13/16 (50), scope expansion 15/13/16 (44), failure to revise 10/11/16 (37). Agents follow memory instead of reassessing it. | §4.3, Figure 4 |
| P6 | Raw trajectories (FullTraj) use about 34% fewer steps and 28% fewer output tokens than NoMem (185.1 → 141.7/114.5/113.1 steps) and 29–35% fewer steps than the five memory systems, at 16.3–32.9M vs 6.45M input tokens. The paper offers lost process information as a *potential* explanation, not a proven cause. | §4.4, Table 2 |
| P7 | Without information isolation NoMem resolves 93.31% ± 0.87% from leaked public solutions; with isolation 73.16% ± 0.61%. | §3 |
| P8 | The authors' own limits: Verified subset only, one agent–model configuration. Appendix F's 29 systems are single runs. | §6, App. F |

Paper design implication (§1, §5, §6): preserve process information and reassess
applicability against the current task context.

## 4. AutoMem fit

| Paper finding | AutoMem surface | Hypothesis to test | Not claimed |
| --- | --- | --- | --- |
| Process information (P6) | Per-memory content limits and optional summarization on the write path (server limits recorded in the Memory Tax spec, #79); hook-captured build/test/deploy events from mcp-automem. | AutoMem recall shows the same step gap to raw trajectories that the paper reports for other memory systems; the gap narrows when stored memories retain execution order. | That compression is the cause (the paper does not prove it). |
| Applicability (P3–P5) | Provenance and `t_valid`/`t_invalid` on recalled memories; a recall-side hook can wrap each result with its source task, date, touched files and superseded flag. | An explicit applicability check lowers Harm on Preservation Tasks without lowering Rescue on Improvement Tasks. | That AutoMem returns an applicability judgement today. It does not. |
| Temporal invalidation | `supersedes_memory_id` sets the older record's `t_invalid`; `current_only=true` suppresses it; recall `end` bounds the window ([maturation contract](maturation.md)). | History often contains a later task that edits or reverts the same code region; suppressing the older fix reduces stale reuse. | That staleness is one of the paper's four modes. It is a separate, additional hypothesis. |

How each paper failure mode maps to the arms (section 5):

| Mode | Targeted by | Expectation |
| --- | --- | --- |
| Compatibility mismatch | applicability pre-check and instruction (A3) | Plausible gain. |
| Misapplied transfer (most common) | applicability instruction; A1 contrast on process information | Uncertain; the paper shows it persists after files are identified. |
| Scope expansion | instruction wording only | Weak. |
| Failure to revise | not targeted | A one-shot start-of-session injection cannot react to contradicting test output; that needs a mid-run re-check hook, listed as a future arm. |
| Superseded history (ours) | `t_invalid` + `current_only` (A3) | Measurable only on base tasks whose history contains a superseding pair; report that n. |

Candidate `verygoodplugins/automem` issues (do not open from here, and do not
claim any exists): recall results that carry applicability metadata for clients,
and a state-labelled evidence packet (see [A-TMA](atma-ltp.md)).

## 5. Arms

All arms share the agent, pinned model ID, prompt, information isolation, turn
budget, container limits and seeds. Use Claude Code at a pinned version; matching
DeepSeek-V4-Flash is not required, so any comparison with paper numbers is
directional only. NoMem in our own runs is the baseline, never a paper figure.

| Arm | Memory exposure |
| --- | --- |
| **A0 NoMem** | None. Closed-book, as in paper §3 and Appendix E.2. |
| **A1 RawTraj** | Complete raw historical trajectories in chronological order, no compression or selection. Trajectories come from the same agent solving the historical tasks *without memory*, as in the paper (Appendix E.1). |
| **A2 AutoMem** | AutoMem as shipped. Memories are built by mcp-automem-style Claude Code hooks while the agent solves the history, at a pinned mcp-automem SHA (this repo's `variants/baseline` pins `4be6724`; choose and record the pin at G0). A task-conditioned recall hook injects results at session start, confirmed against the pinned hook at G0. Stop-hook session summaries are the noise source documented in the [hook-replay notes](../session_2026-04-28_hook_replay.md); record which variant ran. |
| **A3 AutoMem + applicability** | A2 plus two interventions: (a) write-time invalidation: if a later history task edits the same file region as an earlier one (non-test patch hunk overlap, computed only from history that predates the base task), store it with `supersedes_memory_id` and recall with `current_only=true`; (b) a read-time applicability gate: each recalled memory carries source task, date, touched files and superseded flag, a deterministic check drops or flags memories whose files or symbols no longer exist in the base-task checkout, and the hook asks the agent to state, before its first edit, whether each used memory's assumptions hold. |

A3 bundles two interventions on purpose, to answer "does any of this help" at
smoke cost. If Stage 1 shows signal, split it into A3a (invalidation only) and
A3b (applicability only) before any larger claim.

Each base task gets its own memory store, frozen and read-only while the base
task is solved (paper Appendix E.2). History scenarios follow the paper:
**Relevant** (Strong + Weak related, 3–10 tasks) and **Noisy** (Relevant plus
Unrelated, 7–21), capped at 35 tasks. Repo history is out of scope for the smoke.

## 6. Metrics

Use the official verifier and scorer from the release; never a local substitute.

| Group | Metric | Definition |
| --- | --- | --- |
| Functional correctness | Resolved | All-or-nothing official verifier result per run (paper Appendix H.1). |
| | F2P / P2P | Micro-averaged fail-to-pass and pass-to-pass test rates (paper H.2). |
| Step count | Steps | Mean model-response turns per solve, excluding memory-building. Also pre-edit / edit-span / post-edit steps and search/read call counts (paper §4.4). |
| | Tokens | Input and output tokens per solve; **build-time** tokens (history solves, AutoMem writes, embeddings) reported separately per arm. |
| Regressions | Rescue / Harm | Over paired runs: Rescue = NoMem fails and arm succeeds; Harm = NoMem succeeds and arm fails. Rescue − Harm equals the change in Resolved. |
| | Harm on related history | Harm under Relevant history. |
| | Harm added by unrelated history | Paired Harm(Noisy) − Harm(Relevant); Noisy contains Relevant, so the difference isolates the Unrelated tasks. |
| | Unrelated-only control | **Our extension, not in the paper:** history of only the annotated Unrelated tasks. Requires the release to expose those labels. |
| | Attribution | Count a failure as memory-induced only when memory visibly shapes the failing decision or edit (paper §4.3). Tag the four modes plus our `stale_superseded`. Two raters, report agreement; any LLM-assisted tagging follows the [judge policy](../BENCHMARK_JUDGE_POLICY.md) and is spot-checked by a person. |
| AutoMem diagnostics (ours) | Recall precision by label | Share of recalled history from Strong / Weak / Unrelated tasks, per base task. |
| | Hygiene | Injected tokens, recall latency, fraction of recalled memories with `t_invalid` set (expect 0 under A3), per-store memory count, mean content length, write-side summarization rate. |

Statistics: task-level bootstrap CIs (the paper uses 10,000 replicates) on
Rescue, Harm and step differences. Pre-registered comparisons: **H1** A1 uses
fewer steps than A2; **H2** A3 has lower Harm than A2 on Preservation Tasks under
Noisy history without lower Rescue on Improvement Tasks; **H3** within A3,
invalidation removes superseded recalls on the subset of tasks that have a
superseding pair. Select Improvement/Preservation subsets from runs that are
independent of the NoMem reference runs, as the paper does (Appendix E.1), to
avoid regression-to-the-mean artifacts. Small N is directional only.

## 7. Isolation and reporting rules

- **Closed-book.** Replicate the paper's information isolation (web tools off,
  git history and benchmark-private paths blocked). Without it the paper's NoMem
  rate rises from 73.16% to 93.31% on leaked solutions, which erases headroom.
- **No future leakage.** Each store contains only history that predates its base
  task; recall passes an `end` bound at the base-task time; assert that no
  recalled memory comes from the base task's own PR.
- **Local-only AutoMem endpoint**, rejecting non-local URLs, as in the A-TMA plan.
- **Tag gating makes server-side `expand_relations` a no-op** (see `CLAUDE.md`).
  Leave expansion off; use `runners/client_side_expand.py` if expansion is tested.
- **Recall-only during base-task solves.** Capture hooks run only in the history
  phase; the store is frozen afterwards.
- **Label every figure.** Paper numbers appear only as `paper (Claude Code
  2.1.170, DeepSeek-V4-Flash)`; ours as `automem-evals run <id>`. They are never
  put in one unlabeled column and never relabelled as AutoMem results. No AutoMem
  number exists until Stage 1 completes on official artifacts.

## 8. Cost estimate and approval gates

Token anchors below are **paper means** (Improvement Tasks, Relevant history,
Claude Code with DeepSeek-V4-Flash; Table 2). They are planning inputs, not our
measurements, and dollars are not quoted: the paid-budget doc says prices have no
defaults and must be reverified per campaign.

| Anchor per task-run | Input tokens | Output tokens | Steps |
| --- | --- | --- | --- |
| NoMem | 6.45M | 59.5K | 185.1 |
| FullTraj | 16.31M | 50.2K | 141.7 |
| Memory systems (five) | 5.82–6.49M | 57.9–63.9K | 171.8–189.5 |

| Stage | Scope | Planning size | Dollar sensitivity |
| --- | --- | --- | --- |
| 0 (free) | Artifact re-check; fake-only unit tests for the leakage guard, supersession mapping and Rescue/Harm pairing | none | $0 |
| 1 (smoke) | 3 base tasks, 1 run, 4 arms, Relevant history; if historical trajectories are not released, 12 or fewer history solves (pick tasks with 3–4 related tasks) | about 107M input and 0.7M output tokens for the arms, plus about 77M input and 0.7M output if history must be regenerated: about **185M input, 1.4M output** | each $1.00/M of uncached input price adds about $185; each $1.00/M of output price adds about $1.4 |
| 2 (pilot) | **Not sized for approval here.** 7 settings (A0; A1–A3 × Relevant, Noisy) × 12 base tasks × 2 runs is about 1.75B input tokens before history solves | about 1.75B input | each $1.00/M adds about $1,750 |

Prompt caching can cut billed input by a large factor, but cached pricing is not
assumed; Stage 1 must report measured billed tokens and cache hits so Stage 2 can
be re-estimated from data. A full suite is out of scope: 344 Verified base tasks
and 2,987 historical tasks (or the full 555 / 4,869) are never run under this spec.

Gates (all must be explicit, in order):

- **G0 artifacts.** Official data, loader, verifier/scorer, immutable revision,
  checksum and license pinned in section 2. Currently **blocked**.
- **G1 spend guard.** The repository's [capped proxy](paid-budget.md) covers
  OpenAI chat models and Voyage/OpenAI embeddings only. A Claude Code agent loop
  on another provider is not covered, so a reviewed guard (or an owner-approved
  substitute) must exist before any agent call. Embedding and judge calls go
  through the proxy as usual.
- **G2 Stage 1 approval.** Owner approves a fresh ledger, verified prices, a USD
  cap, and a token ceiling of 250M input / 2M output with abort at 80%.
- **G3 Stage 2 approval.** Separate owner decision after reviewing measured
  Stage 1 cost and results.
- **Standing limits.** No server changes (the AutoMem server stays pinned by SHA;
  product needs go to `verygoodplugins/automem` as separate issues), no full-suite
  spend, no merge or auto-merge from the authoring worker.

## 9. Threats to validity

- **Leakage.** Tasks derive from public repositories; isolation reduces but may
  not remove memorization by the model. Report the A0 rate against the paper's
  73.16% only as context.
- **Exposure confound.** The paper's systems differ in how memory reaches the agent
  (tool-driven retrieval, session-start injection, lifecycle hooks). We fix one
  mode, session-start injection, so the result speaks to that mode only.
- **A3 bundles two interventions** until split (section 5).
- **Stock hooks are partial process capture.** A2 measures AutoMem as shipped, not
  an ideal process-preserving store; a per-trajectory distillation build is a later
  variant, not part of this spec.
- **Small N and three runs.** Stage 1 cannot support significance claims.
- **Attribution is subjective.** The paper's own attribution was manual.
- **Paper limits carry over.** Verified subset and a single agent–model setup.

## 10. Follow-up slices (none started here)

1. Re-check the release (free); update the pin ledger.
2. After G0: loader, official-verifier wrapper and isolation guard under
   `runners/memdev_bench/`, fake-only unit tests, local-endpoint rejection.
3. Rescue/Harm pairing analyzer with task-level bootstrap on fixtures.
4. Recall-only hook variant, supersession mapping and applicability gate.
5. Stage 1 smoke, only after G1 and G2.
6. Stage 2 pilot, only after G3; split A3 into A3a/A3b first.

## Sources

- [MemDev-Bench arXiv record (v1)](https://arxiv.org/abs/2610.27524)
- [arXiv HTML v1](https://arxiv.org/html/2610.27524v1)
- [arXiv PDF v1](https://arxiv.org/pdf/2610.27524v1)
- [arXiv non-exclusive distribution license 1.0](http://arxiv.org/licenses/nonexclusive-distrib/1.0/)
- [Capped benchmark API calls](paid-budget.md)
- [Repository maturation contract](maturation.md)
- [A-TMA / LTP tracker](atma-ltp.md)
- [Hook-replay notes](../session_2026-04-28_hook_replay.md)
- [Benchmark judge policy](../BENCHMARK_JUDGE_POLICY.md)
