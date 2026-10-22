# MemDerive AutoMem adapter plan and pilot

Candidate: `opportunity:automem-graph-rag-research-scout` (2026-10-22).
Exploratory work in `automem-evals`; official benchmark claims remain in `automem`.

## Release and duplicate check

[MemDerive v1](https://arxiv.org/html/2610.25373v1), submitted 18 October 2026,
provides 10 scenarios, 4,692 events and 1,503 queries with Datalog answers and
support DAGs. The paper reports that all tested memory systems trail BM25 on
derived state, predominantly through ungathered intermediate inputs, and seldom
refresh implicit changes. These are paper findings, never AutoMem results.

All-state issue and PR searches for MemDerive returned no matches on 2026-10-22.
[MemTrace #51](https://github.com/verygoodplugins/automem-evals/issues/51) audits
evidence use; [StateMemBench #50](https://github.com/verygoodplugins/automem-evals/issues/50)
checks current versus superseded answers. Both are open and artifact-blocked.
[A-TMA PR #58](https://github.com/verygoodplugins/automem-evals/pull/58), merged
5 October, plans state-view/ghost-memory diagnostics. MemDerive adds executable
intermediate gold, dependency-frontier diagnosis and implicit-change trajectories.

The paper's reproducibility links are public and usable:

| Official release | Pin downloaded 2026-10-22 | License |
| --- | --- | --- |
| [DeriveMem-67C6 dataset](https://anonymous.4open.science/r/DeriveMem-67C6/) | `formal-set-v1.16`; ZIP SHA256 `ac72c472645ab2ace3da1666e81673359c15afdf788f52ce5a1ff8425995a84a` | Code Apache-2.0; world data CC BY 4.0 |
| [DerivEval-6799 framework](https://anonymous.4open.science/r/DerivEval-6799/) | ZIP SHA256 `6d066bb65e6a86dfe6bd2b41827c183a02b952aff4bd699cd7341066e04215b3` | Own code MIT; adapted LoCoMo prompts separately CC BY-NC 4.0 |

Credit: Sen Gao, Yongan Li, Han Chen, Bingsheng He, Ming Wu, Jason Zeng,
Michael Heinrich and Shixuan Sun. No dataset or upstream code is vendored.
Shell HTTP returned 403, but Chrome rendered both repositories and downloaded
their ZIPs. This is **not** an unavailable-artifact blocker. The anonymous pages
advertise availability through 2027-08-31; verify archive hashes before reuse.

## Adapter and reproducible scope

[`pilot.py`](../../scripts/benchmarks/memderive/pilot.py) stores only public
Chronicle text, event IDs, source and narrative timestamps. Each run has one
unique tag and a persisted ID manifest. It ingests the prefix through the query
cutoff, recalls per question with an observation `end` bound, then rejects foreign
or future IDs. Redirects and remote endpoints are refused. Cleanup deletes only
manifested IDs, including on failure; it never resets the shared stack.

The adapter returns original public event text for recalled event memories.
Gold answers, symbolic actions, witnesses and diagnostic DAGs remain evaluator
metadata: they never enter memory or the root answer prompt. DAG probe questions
are used only in separately labelled diagnostic calls. Both arms use the official
BM25 implementation (`k1=1.5`, `b=0.75`), v9 reader prompt and v2 deterministic root
scorer, with event documents, top-15 evidence and the same local reader. Node and
edge smoke checks use the framework's `answer_matches` plus answerability; they
do not implement the complete paper failure-frontier/recovery protocol.

Download and extract the two official ZIPs, check the hashes above, and run with
Python 3.11+ (the framework requirement; adapter itself has no new dependencies):

```bash
PYTHONPATH=tmp/memderive/eval/src /opt/homebrew/bin/python3.12 \
  scripts/benchmarks/memderive/pilot.py --data tmp/memderive/data \
  --output tmp/memderive/pilot-final
```

Requires local AutoMem at `localhost:8001` (`AUTOMEM_TOKEN`, default `test-token`)
and an Ollama-compatible reader at `localhost:11434` with `qwen3.5:9b`.
Reader options are temperature 0, seed 0, thinking disabled and 2,048 output tokens.
The local MLX model digest is
`d63f830f28d515fefea546f213fca7a75e9dd5176ef51a6deabc952d1c99a911`.
Each run records input hashes, health/model snapshots, raw prompts/responses,
retrieved event IDs, root predictions/scores and targeted/inherited probe traces.
Errors leave `not_scored`, preserve raw responses and still attempt cleanup.

## Evaluation matrix and graph mapping

| Experiment | Controls and measurements |
| --- | --- |
| Pilot, cold | Smallest full history `tripops_w1` (452 events); `q055`, a five-node/five-edge answerable official `shape-40-v3` DAG. Integration smoke only. |
| Q1 reliability | Plain AutoMem versus BM25; then dependency-following recall as a separate variant. Match reader/prompt, event and token budgets; report answer/answerability/witnessed accuracy, citation P/R/F1, obsolete and distractor citations. |
| Q2 diagnosis | Same official probes for inherited parent context and targeted fresh recall; preserve shared-node edge occurrences. Localize frontier, distinguish ungathered/unretrievable/misderived, and report self-evidence versus gold-evidence recovery separately. Gold recovery is diagnostic assistance. |
| Q3 maintenance | Official 132-question/five-checkpoint panel; replay complete-session prefixes without future leakage. Separate explicit/implicit refresh and unchanged-answer preservation; record ingest/query tokens and latency. |
| Coverage and maturation | Three development worlds before untouched held-out worlds; slice temporal/semantic/closure/rules/set-quant, witness size, obsolete share, DAG height/width. Follow [maturation](../eval/maturation.md): cold first; matured and matured-full separately, never inferred from cold. |

The following is a proposed treatment, not a claim that the pilot builds these edges:

| MemDerive construct | AutoMem mapping and assertion |
| --- | --- |
| Derived state and its premises | `derived -> input` `DERIVED_FROM` edges to every fact, rule version and completeness assertion actually used; preserve source-event provenance and shared dependencies. Never seed the gold DAG as system knowledge. |
| Fact or policy revision | Version rules as memories alongside facts. Use `supersedes_memory_id` where supported; verify `old -> new` `INVALIDATED_BY`, retaining historical nodes. Reversed lifecycle edges suppress the replacement. |
| Validity versus observation | `timestamp` records observation; `t_valid`/`t_invalid` bound the operative fact/rule version. Keep source effective time distinct. Query prefixes and `end` prevent future observations; validity filtering alone cannot do that. |
| Implicit change | Walk reverse `DERIVED_FROM` dependencies from changed premises, invalidate stale derived versions at the change boundary, then recompute and record fresh dependencies. Set old `t_invalid`, new `t_valid`, and old-to-new lifecycle links. Suppression alone is not recomputation. |
| Negation, sets and completeness | Track policy/scope dependencies, including missing-input obligations and completeness versions; a newly inserted member can change an aggregate without touching any formerly cited member. Missing evidence must not silently become justified zero. |

## Server hypothesis and decision

**Hypothesis:** query-time dependency-following recall can recover intermediate
inputs that ordinary similarity retrieval misses. Start with retrieved derived
states/rules, follow their recorded `DERIVED_FROM` inputs with bounded depth and
budget, resolve versions at the requested cutoff, and return provenance and
missing-dependency explanations. Keep run tags during traversal. Existing generic
relation expansion is not evidence of complete derivation gathering.

Test against plain recall and BM25 with equal final context tokens and explicit
expansion cost. A client orchestration control can decompose inputs first, but a
server variant must discover dependencies from its own bank, never the gold DAG.
Maintenance is a separate hypothesis: reverse dependency tracking plus versioned
rules should improve implicit refresh without harming unchanged-state preservation.

**Go** for this adapter and development diagnostics. **No-go** for server changes,
full-suite spending or an AutoMem advantage claim on a one-query smoke. Advance
only after paired dev runs show fewer ungathered failures at matched budgets,
preserve historical/as-of isolation, and improve implicit refresh without reducing
preservation. Set numeric acceptance margins before evaluating held-out worlds.

## Pilot result (2026-10-22)

| Cold arm | Root correct | Witnessed correct | Citation P / R | Targeted nodes | Inherited edges |
| --- | --- | --- | --- | --- | --- |
| BM25 | 1/1 | 1/1 | 0.5 / 1.0 | 4/5 | 3/5 |
| AutoMem | 1/1 | 1/1 | 0.5 / 1.0 | 4/5 | 4/5 |

Both returned `Trip-Tanit receipt export`. Twenty reader calls covered both arms;
all 452 run memories were deleted. A preceding completed run had BM25 inherited
4/5; a later repeat failed JSON parsing at the 1,024-token output cap and remained
unscored with cleanup completed. The final run uses 2,048 tokens. These probe
counts can vary despite seed 0; they support no causal or statistical advantage
claim. No full frontier attribution, recovery intervention, maintenance panel,
matured run, or held-out evaluation was performed. See the
[verification report](memderive-verification-report.md) for commands and evidence.
