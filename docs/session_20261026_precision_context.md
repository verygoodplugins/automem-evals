# Controlled context precision experiment — 2026-10-26

Status: **running; no completed experiment score yet**. This is the one active evaluation batch after the inline obsolete-content fix. [AutoMem #273](https://github.com/verygoodplugins/automem/pull/273) is merged at `fe0d5c374f1da65d30aaa9311e24647284d22793`. [Evidence PR #78](https://github.com/verygoodplugins/automem-evals/pull/78) remains pending hosted review and must only merge once ready.

## Frozen question and condition

Does removing off-label retrieved context improve answers to preference questions? Compare **full retrieved top ten** with an **order-preserving subset containing only retrieved support-labeled sessions**. Never insert missing support. Both arms share one ingestion and one recall per question; every other setting, prompt template, model and scoring policy stays fixed.

The cohort contains all 30 single-session-preference questions and five historical support-miss controls. `d6233ab6` overlaps, producing **34 unique questions**. The preference stratum and the five controls will be reported separately. Selection and alternating arm order were frozen before provider preflight or experiment calls.

The [preregistration](../data/results/precision-context-20261026/preregistration.json) SHA256 is `d945394ec62469d8e92c851ccd6a9ce11b133ddd8b59bc9a46e7333d3dc452d8`. It binds all question/item hashes, server/harness revisions, models, condition, arm order and budget. The [manifest](../data/results/precision-context-20261026/MANIFEST.json) binds one-off execution sources and points to receipts and raw evidence.

## Comparison and limits

Use the merged server with the official harness frozen at `3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876`, canonical `baseline` configuration, fresh per-session ingestion, Voyage-4/1024d, recall limit ten and exact question scopes. Enrichment, JIT, consolidation, graph expansion, decomposition, temporal hints and answer-focus prompting are off. The answerer is `gpt-5-mini`; judge is `gpt-5.4-mini-2026-03-17`; native chain-of-note prompting and retry policies are unchanged.

**Fresh full-context answers are the paired control.** The historical [post-merge baseline](session_20261022_postmerge_baseline.md) and its grades remain unchanged. Historical prompt bytes/full recalled texts were not retained, so this is a fresh paired replay rather than a claim of exact historical prompt reconstruction. The native result, not the older scratch preference-rank table, supplies the cohort and historical evidence.

Support-session labels are not exhaustive relevance judgments. The treatment is an oracle diagnostic, not a deployable filter or a true relevance-precision measurement. It changes context length as well as off-label content. One stochastic pass per arm cannot establish repeatability or a whole-benchmark accuracy claim. No alternate prompt, judge rubric, ranking rule or graph condition is added to this batch.

## Evidence and safeguards

Retain full recall envelopes, both context lists, canonical prompt text/hashes, every model request/raw response, parsed answers, judge rationales, timings and per-case status. The append-only model journal preserves failed/ambiguous work. Completed question/arm checkpoints can be resumed under the same bound contract; interrupted ingestion requires an explicit reviewed new attempt. Partial files never supply a headline score.

The authenticated loopback proxy passed all three provider preflights. A **$3 subledger** carries forward **$9.809397650** of original accounted spend, including prior ambiguous liabilities, within the original **$20 total ceiling**. All preflight, ingestion/query embeddings, answers, judges and native retries share that subledger. Accounting failure or halt stops owned execution; provider credentials remain inside the proxy.

The native controller owns API/benchmark processes and disposable FalkorDB/Qdrant stores. It cleans them on completion or failure. A bound completion hook records the completed or explicitly incomplete outcome; a separate verified-PID watcher closes accounting and stops only the owned proxy. Runtime receipts and status live in `data/sweep_runs/precision-context-20261026/`; the completion hook updates this report and the registry locally. No production store, official baseline or product code is changed by this experiment.

## Next action

Finish this one batch and reconcile discordant preference answers and the historical miss controls. Keep any proposed product filter, the matched graph-on/graph-off comparison, AutoMem #270, broader #31 work, AMB/BEAM refresh and architecture changes parked until the result is reviewed.

<!-- COMPLETION-STATUS -->
