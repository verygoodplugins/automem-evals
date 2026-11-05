# MEME — multi-entity and evolving memory: Cascade / Absence / Deletion adapter plan

Track: tracking issue pending; its body is the [acceptance checklist](#acceptance-checklist-tracking-issue-body) below (highest existing issue/PR number on 2026-11-04 was #84). Related: [#67](https://github.com/verygoodplugins/automem-evals/issues/67) / [PR #68](https://github.com/verygoodplugins/automem-evals/pull/68) (StreamMemBench, same `INVALIDATED_BY` + `t_invalid` supersession convention), [StateMemBench #50](https://github.com/verygoodplugins/automem-evals/issues/50), [ForgetEval #31](https://github.com/verygoodplugins/automem-evals/issues/31), [Veracium #62](https://github.com/verygoodplugins/automem-evals/issues/62), [BEAM `knowledge_update` #14](https://github.com/verygoodplugins/automem-evals/issues/14). Candidate: `opportunity:automem-graph-rag-research-scout`. Those probe other behaviors and stay separate experiments.

## Source and availability, checked 2026-11-04

| Artifact | Pin / availability |
| --- | --- |
| [Paper](https://arxiv.org/abs/2605.12477) | v1 only (submitted 2026-05-12); NeurIPS 2026 Evaluations and Datasets Track per the dataset card and repo README. |
| [Project page](https://seokwonjung-jay.github.io/meme-eval/) | Links paper, code and dataset; source of the per-system table below. |
| [Code `MEME-public`](https://github.com/SeokwonJung-Jay/MEME-public/tree/a4f10db14ca14edd698374fa79ad6e1cfd1caf28) | Pinned at `a4f10db14ca14edd698374fa79ad6e1cfd1caf28`; MIT. The two newest commits (2026-11-03) are README edits per their messages. `code/agents/base.py` defines the memory interface; `code/eval/run_agent.py` and `judge.py` are the runner and judge; `results/judge_audit_144.json` is the authors' judge audit. |
| [Dataset `meme-benchmark/MEME`](https://huggingface.co/datasets/meme-benchmark/MEME/tree/e14c4e685772014deb96f91dc7eddfbeb21d90d8) | HF revision `e14c4e685772014deb96f91dc7eddfbeb21d90d8`; CC BY 4.0, ungated. Default config `filler32k` = `meme_filler32k.json`, 20,177,963 bytes, SHA-256 `a88d28374a002b3e5b1683fb7201d06a1ce739d2ebf94c971c37bb65cf6ebdd3` (equals HF's LFS id; re-downloaded and re-hashed locally). `filler128k` has 40 episodes, `nofiller` 100. Fillers come from LongMemEval and ShareGPT 52K: keep the dataset card's attribution and never commit the data. |

Duplicate check: a search of this repository's issues and PRs (open and closed) for `MEME` returned 0 results, and none of the 84 issues/PRs mention `2605.12477`, `meme-eval`, `MEME-public` or `multi-entity`.

## What MEME measures

100 episodes (50 personal-life, 50 software-project), about 35K tokens each, 17–27 sessions. All entity values are fictitious. Verified from the pinned JSON: **694 post-change questions** (332 + 362) and 494 pre-change state checks.

| Task | Post / pre-change n | Judge credit (upstream `judge.py` at the pin) | Trivial-pass |
| --- | --- | --- | --- |
| Exact Recall (ER) | 100 / 100 | Gold is a verbatim substring (case/whitespace-insensitive); deterministic, no LLM call. | No |
| Aggregation (Agg) | 100 / – | Every target value present. | No |
| Tracking (Tr) | 100 / – | Full history in chronological order. | No |
| Deletion (Del) | 100 / 100 | Must not reveal the deleted value; "I don't have that information" passes, "it was deleted: X" fails. | Yes |
| Cascade (Cas) | 164 / 164 (hop 1: 100, hop 2: 64) | New value as the sole, definitive answer. Old+new, hedging, future tense and "I don't know" fail. | Yes |
| Absence (Abs) | 130 / 130 (hop 1: 100, hop 2: 30) | Expresses uncertainty or questions validity. Confidently stating the old value fails. | Yes |

Protocol (pinned data): sessions arrive chronologically. The pre-change block is asked after session index `p` (12–22) and the post-change block after the last session. `position_after_session` is a 0-based inclusive index (200/200 blocks fall in `[session[p], session[p+1])`). For Cas/Abs/Del, credit also needs the same slot's pre-change question answered correctly (trivial-pass); denominators stay the full post-change counts and the judge labels each as `real_pass`, `trivial_pass`, `knew_but_failed` or `never_knew`. The project page's Overall equals the unweighted mean of the six task accuracies (checked on the BM25 0.25, text-emb 0.33 and MD-flat 0.42 rows). Every system gets one native retrieval per question, then a shared answerer (upstream prompt, temperature 0, 500 max tokens); the judge is GPT-4o at temperature 0.

Paper-reported baselines (project page; `gpt-4.1-mini` as internal and answering LLM, 100 episodes, about 32K filler). **These are not AutoMem results.**

| System | ER | Agg | Tr | Del | Cas | Abs | Overall | Ingest / inference $ per episode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BM25 | 1.00 | 0.05 | 0.16 | 0.27 | 0.02 | 0.00 | 0.25 | – / 0.04 |
| text-embedding-3-small | 0.96 | 0.33 | 0.46 | 0.17 | 0.04 | 0.00 | 0.33 | – / 0.03 |
| Mem0 | 0.67 | 0.35 | 0.43 | 0.21 | 0.03 | 0.00 | 0.28 | 0.10 / 0.01 |
| Graphiti | 0.03 | 0.01 | 0.04 | 0.09 | 0.02 | 0.01 | 0.03 | 0.55 / 0.00 |
| MD-flat (file-based) | 0.94 | 0.45 | 0.77 | 0.25 | 0.06 | 0.05 | 0.42 | 0.04 / 0.01 |
| Karpathy Wiki | 0.11 | 0.18 | 0.27 | 0.03 | 0.01 | 0.02 | 0.10 | 1.17 / 0.22 |
| Average of the six | 0.62 | 0.23 | 0.35 | 0.17 | 0.03 | 0.01 | 0.24 | – |
| MD-flat × Opus 4.7, **20-episode subset** | 0.60 | 0.80 | 0.20 | 0.80 | 0.32 | 0.59 | 0.55 | 3.87 / 0.66 |

"Collapse" in the abstract is the six-system average (Cascade 3%, Absence 1%) despite adequate static retrieval (BM25 ER 1.00). Closure with Opus 4.7 is a 20-episode subset result, "at ~70x the baseline cost" per the abstract. We did not reconcile that ratio with the rounded per-episode costs above and do not restate one. Per the paper's §4.3 failure analysis, the change event is out-ranked by the pre-change value on vector retrievers and never surfaced on tool-use, graph and sparse retrievers (Graphiti stores the rule, value and change event as edges, but only the rule and old value make the top-k), so the answerer reports the earlier value. Closure appears when Opus 4.7, as MD-flat's internal LLM, writes the propagated value into the store at ingest. The AutoMem question is whether typed edges plus `t_invalid` get the change event or a propagated value into the single retrieval without Opus-class write cost.

## Proposed AutoMem adapter

Implement `scripts/benchmarks/meme_automem_adapter.py` against the pinned `BaseMemorySystem` and run it through the upstream `run_agent.py` and `judge.py` unchanged. Do not modify the official scorer.

| Hook | AutoMem mapping and verification |
| --- | --- |
| `ingest_session` | Read only `session_id`, `timestamp`, `conversation` (`adapter_view` in the smoke script). Never read session `type` (evidence/filler), `tasks`, `root`, `root_change`, `dependency_edges_used`, `evidence_session_indices`, task `notes` or question blocks. Store the dataset `timestamp` (`/memory/batch` maps it to `t_valid`, per `runners/beam_retrieval_eval.py`), never wall-clock, under tag `meme:<run>:<episode_id>`. Ingest in order, and only through session `p` before the pre-change block (`ingest_schedule`). |
| `finalize_ingest` | Cold: drain the enrichment queue. A matured variant follows [maturation.md](maturation.md) with `reference_time` set to each block's question time; the post-change pass must not alter state the pre-change block saw. |
| `retrieve` | Exactly one `/recall` per question (upstream query budget = 1), frozen `limit`, tag-isolated. Follow edges only inside that response: `runners/client_side_expand.py` reads `results[].relations[]` and makes no second call. Do not assume server-side `expand_relations` crosses tag gates. The returned string serializes invalidated records explicitly (see below). |
| `answer_question` | Not overridden: shared upstream prompt and answerer. |
| `get_memory_snapshot` / `get_retrieved_context` | Plain-text dump of adapter-owned records with `t_valid`, `t_invalid` and edges (W-check); the exact string `retrieve` returned (R-check). |
| `reset` | Delete only UUIDs the adapter created. Loopback endpoint only; fail on HTTP or protocol errors. |

Arms use identical sessions, answerer, judge, `limit` and seeds, and change one thing at a time:

| Arm | Write path | Purpose |
| --- | --- | --- |
| M0 verbatim | One memory per session, no edges. | Floor and ER control. Cannot satisfy Deletion: `t_invalid` on a session memory hides still-valid facts too. |
| M1 fact units | Atomic facts from a disclosed internal LLM (ADD-only, mem0-style prompt as in `runners/beam_shim_v2.py`), `t_valid` = session time. | Supersession needs fact-level units. |
| M2 supersession | M1 + same-slot replacement and explicit-removal handling from observed text. | Tracking, Deletion, stale-value suppression. |
| M3a edges | M2 + rule, dependent and change-event edges, expanded inside the single recall. | Does retrieval deliver the change event? |
| M3b write-time resolution | M3a + an internal LLM resolves dependents when a change event is ingested. | Mirrors the paper's closure mechanism. Report as AutoMem plus an external LLM, never "AutoMem alone". |

Mapping of the three new tasks (plus the Tracking conflict):

| Task | Write-time record | Edge / invalidation | What to instrument |
| --- | --- | --- | --- |
| Deletion | User removes a slot value: set `t_invalid` on the fact record(s) holding it. Store the request as a value-free tombstone ("user removed their `<slot>`"). | Control D2: hard `DELETE` of the same UUIDs. | The judge fails any answer that reveals the value, even "was deleted", so a verbatim removal turn or an annotated-but-shown value fails. Suppress with `current_only=true`. |
| Absence | Rule stated with no replacement: when its source slot changes, set `t_invalid` on dependents and store an uncertainty record ("`<slot>` was `<v>`; unverified after `<source>` changed"). | `INVALIDATED_BY` old → uncertainty; `DERIVED_FROM` uncertainty → rule, change event. | Passes only if the pre-change check was right, but an always-abstain policy raises Absence while lowering Cascade: report both together with ER/Agg/Tr as guard metrics. |
| Cascade | Rule stated with a replacement: M3a links rule ↔ dependent fact and rule ↔ change event with `RELATES_TO` (strength at least 0.6); M3b writes the propagated value. | M3b: `INVALIDATED_BY` old → new, `DERIVED_FROM` new → rule, change event. | Judge needs the new value alone, so context holding old value, rule and change event relies on the answerer reasoning. Client expansion is one hop (`max_per_seed` 3): hop-2 (64 Cas, 30 Abs) needs depth-2 expansion or transitive writes. Report hop 1 and 2 separately. |
| Tracking | Keep superseded values ordered by `t_valid`. | `INVALIDATED_BY` chain gives order. | Needs history, which `current_only=true` removes. |

**Invalidation reasons.** Superseded, removed and unverified records all look like "`t_invalid` set", so the adapter writes `metadata.invalidation_reason` as `superseded`, `removed` or `unverified`, derived only from observed text. `retrieve` shows superseded values as past (with the successor), omits removed values entirely, and shows unverified ones as uncertainty. That resolves the Tracking/Deletion conflict without per-task routing, which would leak the task label. `INVALIDATED_BY` is not in the client-expansion allow-list, so the adapter reads `t_invalid` and the reason directly and uses `RELATES_TO`/`DERIVED_FROM` for expansion.

**Leakage and tuning controls.** Slot names come from conversation text, not the `entity` field. Freeze prompts, rules and thresholds on a dev slice (the first 10 episodes per domain by `episode_id`) before any scored run, and report all 100 (the paper's denominator) plus the held-out 80. Use synthetic fixtures for extraction, edge direction (old → new), reason handling and one-recall-per-question. Gold labels may be used only afterwards: compare invalidated records against `chain_entities`/`filler_entities` to report over-invalidation, never fed back.

## Gates and cost

- **G0 wiring (done, free):** the smoke below.
- **G1 spend guard:** `scripts/benchmarks/paid_budget_proxy.py` supports only `gpt-5-mini`, `gpt-5.4-mini-2026-03-17`, `voyage-4` and `text-embedding-3-small` ([paid-budget.md](paid-budget.md)). The paper's `gpt-4.1-mini` answerer/internal LLM, the GPT-4o judge and an Anthropic internal LLM for an Opus 4.7 M3b arm are not routable, and unsupported calls halt the campaign. A paper-comparable column needs a separate proxy change with verified prices and an Anthropic lane. Otherwise run proxy-supported models and publish them as a non-comparable column; never mix the two.
- **G2 cap:** no spend is approved and no AutoMem cost estimate is given here; the paper's per-episode figures show only scale. Stages: S1 dev slice (20 episodes) M0+M1; S2 all 100 episodes M0–M3a cold, then matured; S3 M3b, with an Opus-class internal LLM only on a 20-episode subset like the paper.

## Reporting contract

Every result file must carry the fields below. `python3.12 scripts/benchmarks/meme_wiring_smoke.py --check-contract <result.json>` enforces the accuracy, disclosure and cost fields (key names: `contract_errors` and the `scored_result()` fixture in `test_meme_wiring_smoke.py`); the failure list, diagnostics and labelling rules are reviewed by hand. For a subset it also bounds each task's `n` by the selected episodes (ER/Agg/Tr/Del exactly one question per episode; Cas/Abs one hop-1 plus zero or one hop-2, so leaving out an episode removes at most one hop-2 question; measured on the pinned file), but it cannot verify which episodes were selected, since the contract carries no episode ids.

- Per-task accuracy with `correct` and `n` for ER, Agg, Tr, Del, Cas, Abs (full run: 100/100/100/100/164/130), Overall as the unweighted mean of the six, hop-1/hop-2 splits for Cas/Abs, and `real_pass`/`trivial_pass`/`knew_but_failed`/`never_knew` for Cas/Abs/Del. Failures and skips count as incorrect and are listed.
- Disclosure: answerer, judge (default GPT-4o with the pinned upstream prompts, temperature 0), internal LLM or `null`, embedding model, AutoMem server commit and config (`limit`, `current_only`, expansion, enrichment), arm, cold or matured, dataset revision and subset flag. A different judge or answerer is a different column. `paper_comparable` is true only for `gpt-4.1-mini`, `gpt-4o`, all 100 episodes and the pinned revision.
- Cost in USD: ingest and inference per episode (as the paper), judge total separately, token and call counts, with Opus-class arms stated against M1 only if measured.
- Diagnostics apart from headline numbers: W/R/U checks, ER/Agg/Tr guard metrics, over-invalidation audit, raw per-question judgements.
- Status `wiring_only` carries no accuracy. Paper rows stay labelled paper-reported; the 20-episode Opus row is never compared row-wise with 100-episode rows.

## Executed wiring smoke; AutoMem not run

`scripts/benchmarks/meme_wiring_smoke.py --dataset <meme_filler32k.json>` is offline and makes no model, network or AutoMem calls. It checks the pinned size and SHA-256, 100 episodes (50/50), the 694/332/362 split, per-task and hop counts, 494 pre-change questions, a before-question for every Cas/Abs/Del question, chronological timestamps and unique session ids, the `position_after_session` semantics, the adapter's input allow-list and ingest schedule. Reports hold only counts and hashes, so they are byte-deterministic.

On 2026-11-04 it exited 0 on the pinned file, two runs were byte-identical, and `report_sha256` was `527342f0d79954093270b8ae4385bfabfc796803d1b27d7fb62b295223353eff`. The upstream `run_agent.py`/`judge.py` were **not** run: even BM25 needs an answering LLM and the judge needs GPT-4o, so MEME has no zero-model upstream path like StreamMemBench's. This verifies the data contract, not upstream code wiring. **No AutoMem score or paper-comparable result is claimed.**

```sh
python3 -c "from huggingface_hub import hf_hub_download as d; d('meme-benchmark/MEME','meme_filler32k.json',repo_type='dataset',revision='e14c4e685772014deb96f91dc7eddfbeb21d90d8',local_dir='.agent-drafts/meme-data')"
python3.12 -I scripts/benchmarks/meme_wiring_smoke.py --dataset .agent-drafts/meme-data/meme_filler32k.json --output .agent-drafts/meme-wiring-smoke.json
python3.12 -m unittest discover -s scripts/benchmarks -p 'test_meme_wiring_smoke.py'
```

Registry source: `docs/experiments/registry.json`, experiment `EXP-MEME`. As in PR #68, the canonical `STATUS.md`, `index.json` and `scoreboard.html` were refreshed in a scoped way: the prior committed index is the captured input, the new thread and this artifact are added, and `refresh_dashboard.py` renders the three views. `snapshot_context` in the JSON discloses that other threads, scores, worktrees and PRs keep their 2026-11-02 snapshot. Other open PRs also edit these files, so after a rebase restore the three views from the new base and rerun this once (Python 3.12, repository root; it is not idempotent):

```sh
python3.12 - <<'PYTHON'
import copy, importlib.util, json, sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("refresh", root / "data/results/postmerge-20261022/refresh_dashboard.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)
from scripts import experiment_index as indexer

out = root / "docs/experiments"
index = json.loads((out / "index.json").read_text(encoding="utf-8"))
prior = index["generated_at"]
thread = copy.deepcopy(next(t for t in indexer.load_registry(root) if t["id"] == "EXP-MEME"))
artifact = indexer.summarize_artifact(root, root / "docs/eval/meme.md")
thread.update(artifact_count=1, artifact_samples=[artifact["path"]], worktree_status={"state": "not-scanned"})
index["threads"].insert(0, thread)  # registry order: newest first
index["artifacts"].append(artifact)
index["status_counts"] = dict(Counter(t["status"] for t in index["threads"]))
index["generated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
index["snapshot_context"] = {"refresh_scope": ["EXP-MEME"], "retained_snapshot_generated_at": prior,
                             "retained_sections": ["other threads and artifacts", "scores", "worktrees", "prs"]}
refresh.ROOT = Path(index["artifact_overlay_root"])  # captured value; nothing was re-scanned
refresh.write_with_provenance(index, out / "STATUS.md", out / "index.json", out / "scoreboard.html")
PYTHON
```

## Acceptance checklist (tracking issue body)

Title: `track: MEME multi-entity and evolving memory eval, Cascade/Absence/Deletion (arXiv:2605.12477, NeurIPS 2026 E&D)`

- [ ] Choose the spend path (G1): extend the proxy for a paper-comparable column, or run supported models as a non-comparable one.
- [ ] Implement the adapter hooks above with unit tests: old → new edge direction, invalidation reasons, no future-session ingestion, label-field exclusion, one `/recall` per question, over-invalidation audit.
- [ ] Owner-approved cap, then the S1 dev-slice run (M0, M1).
- [ ] S2: all 100 episodes, M0–M3a cold, then matured per [maturation.md](maturation.md).
- [ ] S3: M3b with a disclosed internal LLM; Opus-class only on a 20-episode subset, cost measured.
- [ ] Publish per the reporting contract; no AutoMem score before an actual run.
