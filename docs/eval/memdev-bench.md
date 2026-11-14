# MemDev-Bench — memory applicability and process preservation for code agents

Status: **spec only, artifact-blocked. No adapter, no paid run, no AutoMem
score.** Written 2026-10-30; artifact checks re-run 2026-11-01. Exploratory and
internal; official benchmark claims stay in `automem` ([REPO_BOUNDARY](../REPO_BOUNDARY.md)).

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

Dedup: on 2026-10-30 a search of this repository's issues and PRs for `MemDev`
returned 0 results. A re-run on 2026-11-01 over all states found nothing that
names MemDev-Bench, arXiv 2610.27524, MemCalib or arXiv 2609.24259 except draft
PR #80, an auto-preserved branch titled with the raw task prompt (so a title
search misses it) that holds this spec file. No tracking issue exists yet. This
is one new file. It does not edit `registry.json` or
the generated dashboard files: #77 and #79 both append to `registry.json` and
regenerate `STATUS.md`, `index.json` and `scoreboard.html`, so a third registry
PR would conflict. Add a parked `EXP-MEMDEV-BENCH` record once those land or G0
clears.

## 2. Release status — blocked on official artifacts

**Decision as of 2026-11-01 (unchanged since 2026-10-30): do not build a
substitute benchmark, adapter or AutoMem score.**

| Checked source | Finding on 2026-10-30 (re-check in the last row) |
| --- | --- |
| [arXiv record](https://arxiv.org/abs/2610.27524) | v1 only (a v2 URL returns 404). cs.AI, 12 authors, no comments field. Links no code, dataset, Hugging Face or project page. Its license link covers the paper, not benchmark artifacts. |
| [arXiv HTML v1](https://arxiv.org/html/2610.27524v1) and [PDF](https://arxiv.org/pdf/2610.27524v1) (text extracted locally) | No MemDev-Bench repository, data or Hugging Face URL. The Reproducibility Statement points to the method sections and appendices, not to a release. The Ethics Statement says the data comes from public GitHub repositories and that licenses are respected, without naming a benchmark license. The only GitHub links are bibliography entries for third-party tools and memory systems. |
| GitHub repository search (`MemDev-Bench`, `memdev-bench`, `MemDevBench`) | Two hits, both unrelated memristive-device benchmarks (`JK1234567899999/memdevice-bench`, `TannerRobison/MemDevice_Benchmark`). Neither is an author release; do not pin them. |
| Hugging Face dataset search (`memdev`) | Empty result. |
| Web search for the exact title plus `github` | No author repository found. |
| Re-check on 2026-11-01 | arXiv still lists v1 only, no comments field and no external links. Hugging Face dataset search `memdev` is still empty. GitHub repository search `MemDev-Bench in:name,description,readme` returns 12 repositories, none a MemDev-Bench release (two are the memristor repos above; `KaiWU5/Awesome-AI4AI` is a paper catalog). |

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

### 4.1 Store construction (write-side mapping)

Each historical task becomes memories in a per-base-task store (section 5). A2
keeps whatever the stock hooks write. A3 adds a deterministic post-pass over the
same store (no model calls) that writes the edges and invalidations below. The
harness runs history solves one at a time, so it knows which task each memory
came from. Relevance annotations choose *which* history is loaded; they never
become tags, content or edges, because an edge derived from a label would leak
the answer and score the annotation instead of AutoMem. Every edge comes from
observable history: patch hunks, merge times, task order.

| History fact | A3 post-pass write |
| --- | --- |
| A task's session-summary memory and its hook-captured event memories | Summary `DERIVED_FROM` events, so process detail stays one hop from the summary. |
| Two history tasks edit overlapping non-test hunks | `RELATES_TO` between their memories, strength from the hunk-overlap ratio. |
| A later task's pre-image lines were introduced by an earlier task | `DERIVED_FROM`, later → earlier. |
| A later task rewrites or reverts an earlier task's hunk | `supersedes_memory_id=<earlier>` with `supersede_relation=INVALIDATED_BY` (old → new, as in [A-TMA](atma-ltp.md)), which sets the earlier memory's `t_invalid` to the later merge time. Recall uses `current_only=true`. |

Server-side `expand_relations` is a no-op under tag gating (section 7), so edges
act only through client-side expansion (`runners/client_side_expand.py`:
`RELATES_TO` and `DERIVED_FROM` are in its default allowed set, `INVALIDATED_BY`
is not; defaults are strength ≥ 0.6 and at most 3 per seed). The hypothesis is
that a flat recall list lacks applicability context (what later changed or built
on a memory) and edges carry it. Edges can also pull in more history, so report
injected tokens next to Harm.

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
| **A3 AutoMem + applicability** | A2 plus three interventions on the same store: (a) write-time invalidation: if a later history task edits the same file region as an earlier one (non-test patch hunk overlap, computed only from history that predates the base task), store it with `supersedes_memory_id` and recall with `current_only=true`; (b) authored `RELATES_TO`/`DERIVED_FROM` edges (section 4.1) read through one-hop client-side expansion; (c) a read-time applicability gate: each recalled memory carries source task, date, touched files and superseded flag, a deterministic check drops or flags memories whose files or symbols no longer exist in the base-task checkout, and the hook asks the agent to state, before its first edit, whether each used memory's assumptions hold. |

A3 bundles three interventions on purpose, to answer "does any of this help" at
smoke cost. If Stage 1 shows signal, split it into A3a (invalidation only), A3b
(edges only) and A3c (applicability only) before any larger claim.

Each base task gets its own memory store, frozen and read-only while the base
task is solved (paper Appendix E.2). The release's relevance annotations choose
the loaded tasks and nothing else:

| History arm | Loaded tasks | What it separates |
| --- | --- | --- |
| None | nothing (A0) | the baseline |
| Relevant | Strong + Weak related, 3–10 tasks (paper) | help or harm when the right history is present |
| Noisy | Relevant plus Unrelated, 7–21 tasks, capped at 35 (paper) | cost of distractors: paired Harm(Noisy) − Harm(Relevant) |
| Unrelated-only | annotated Unrelated tasks only (**ours**, not in the paper) | pure unreassessed reuse: any Rescue is chance or leakage, any Harm is reuse without an applicability check |

Repo history is out of scope for the smoke. Stage 1 runs Relevant only, Noisy
starts at Stage 2, and Unrelated-only needs settings Stage 2 does not size, so it
is a later add-on.

## 6. Metrics

Use the official verifier and scorer from the release; never a local substitute.
Headline metrics are reported per arm and history arm against A0 from the same
runs, never against paper figures:

| Headline | Definition |
| --- | --- |
| Pass-rate delta vs no-memory | Paired change in Resolved from A0 per base task; equals Rescue − Harm. |
| Regression rate on solvable tasks | Harm restricted to **solvable** base tasks: those A0 resolves in every selection run, where the selection runs are independent of the A0 runs used for the comparison (the paper's Preservation Tasks). The share the arm fails. |
| Step count | Mean Steps per solve (below); H1 compares A1 with A2. |
| Applicability reassessment | **Reassessment rate:** share of runs with at least one recalled memory where, before its first edit, the agent assesses whether that memory fits the current checkout (names a file, symbol or version it checked, or states a mismatch). **Rejection precision:** among recalled memories that are Unrelated-labelled or have `t_invalid` set, the share the final edit does not rely on. Reported next to Resolved, since asserting applicability is not the same as being right. A0 has no value. |

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
superseding pair; **H4** A3 has a higher Reassessment rate than A2, concentrated
on Unrelated or superseded memories. Select Improvement/Preservation subsets from runs that are
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

### Pilot command (planned interface; nothing below exists yet)

`runners/memdev_bench/` is not written before G0 (section 10). This is the shape
Stage 1 must have so that spend is bounded by construction:

```bash
python3.12 -m runners.memdev_bench.pilot \
  --release-lock data/memdev-bench/release.lock.json \
  --repo <one repository from the release> --base-tasks 3 --runs 1 \
  --arms A0,A1,A2,A3 --history relevant --max-history-solves 12 \
  --automem-url http://127.0.0.1:8001 --ledger /absolute/memdev-pilot.sqlite3 \
  --max-input-tokens 250000000 --max-output-tokens 2000000 --abort-at 0.8
```

Required behaviour: a dry run by default (prints per-arm token ceilings, exits 0,
zero spend) and a separate `--execute` flag as the only path to a model call.
It refuses to start unless the release lock carries every pin from section 2, the
ledger is fresh and a reviewed agent-loop spend guard (G1) is configured. It
rejects non-local AutoMem URLs. One repository, at most 3 base tasks and 12
history solves: flags may lower these ceilings, never raise them. It aborts at
80% of either token ceiling, marks partial output `incomplete`, and prints no
AutoMem score and no paper figure. The repository is chosen at G0: one with at
least 3 base tasks whose history has 3–4 related tasks.

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
- **A3 bundles three interventions** until split (section 5).
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
6. Stage 2 pilot, only after G3; split A3 into A3a/A3b/A3c first.

## 11. Secondary lead — MemCalib (arXiv:2609.24259)

[MemCalib](https://arxiv.org/abs/2609.24259) (cs.LG, v1 2026-09-21, v3
2026-10-08) asks a narrower question: given memory in context, does the model
give each atomic proposition the right influence, from ignore (A) through bounded
(B) to controlling (C)? It reports that frontier models over-use and under-use
memory. Unlike MemDev-Bench its artifacts are public. It is a **secondary lead,
not a substitute**: single-turn answers scored by an LLM judge, no repository
state and no execution, so it says nothing about regressions on solvable coding
tasks. No MemCalib number may be reported as a MemDev-Bench result, and neither
may be reported as an AutoMem result before our own run.

| Artifact | Revision | License | State |
| --- | --- | --- | --- |
| Paper | arXiv:2609.24259v3 | arXiv non-exclusive distribution license | pinned |
| Code: [`Quark-Medical/MemCalib`](https://github.com/Quark-Medical/memcalib), the paper's "Code and data" footnote | `main` HEAD `8eb018c18e9da84ba24fc2278a3ed5f906e80e47` (2026-09-23, root commit "Release MemCalib code") | Apache-2.0 | pinned. A verl-based RL recipe; `recipe/memcalib_credit/` holds trainer, data, judge and metrics modules, and I found no standalone inference entry point there. |
| Data: [`ZiLaotou/MemCalib`](https://huggingface.co/datasets/ZiLaotou/MemCalib) | `70050dd3fe824ad66c156a5bf67f87944ef38cd7` (2026-09-23) | CC BY-SA 4.0, per-source licenses in `ATTRIBUTION.md` | pinned; file checksums not recorded, nothing was downloaded |
| Judge | `recipe/memcalib_credit/judge.py` at the code pin ("Bailian ordered-usage Judge") | code license above | calls Alibaba Bailian with a DashScope key (README); outside the repository's [capped proxy](paid-budget.md) |

From the dataset card and the Hugging Face API on 2026-11-01: 15,000 examples
(`train.jsonl` 13,500, `test.jsonl` 1,500) over health, general and coding
sources; fields `id`, `domain`, `question`, `memory_blocks`, `memories` (atoms
with `u_star`, `memory_action`, `parent_memory_id` and a usage rubric) and
`source_dataset`. In the first test row the question is a coding question and the
memory blocks mix unrelated personal details with one atom whose `u_star` is C.

Possible AutoMem fit (proposal; nothing is built):

1. **Recall-only diagnostic, no answer model.** Ingest each example's blocks into
   a per-example scope, recall with the question, and report the share of recalled
   blocks holding a C-level atom versus only A-level atoms. This tests whether
   AutoMem injects distractors, not how a model uses them. Embedding calls go
   through the capped proxy.
2. **Answer-and-judge leg** comparing provided blocks, AutoMem-recalled blocks and
   no memory. Blocked: the release judge is a Bailian call the proxy does not
   cover, and another judge needs its own validation under the
   [judge policy](../BENCHMARK_JUDGE_POLICY.md).

The over-use/under-use framing resembles MemDev-Bench's "agents follow memory
instead of reassessing it" (P5). That is a plausible link, not one either paper
demonstrates. Before any run: download outside the repository tree (CC BY-SA 4.0
share-alike reaches derived data, so never commit the data or memory dumps built
from it), record SHA-256 of both files, and open a separate tracking issue; none
exists.

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
- [MemCalib arXiv record (v3)](https://arxiv.org/abs/2609.24259), [HTML v3](https://arxiv.org/html/2609.24259v3)
- [MemCalib code](https://github.com/Quark-Medical/memcalib), [dataset card](https://huggingface.co/datasets/ZiLaotou/MemCalib)
