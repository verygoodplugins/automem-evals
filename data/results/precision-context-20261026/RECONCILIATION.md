# Precision diagnostic: retrospective review, 2026-11-02

The saved 34-question/68-answer batch is valid for a **limited retrospective answer-content diagnostic**. The original automated run and proxy-closure receipts remain incomplete. This review does not make them successful runs, change any grades, or supply an official benchmark score. Machine-readable facts and evidence hashes are in [AUDITED_RESULTS.json](AUDITED_RESULTS.json).

## What the audit established

All 34 ingestion checkpoints and successful recalls match the dataset and question scopes. All 68 prompts reconstruct byte-for-byte from the pinned harness; answer parsing, arm order, exact ordered support subsets and all 152 captured model calls verify against their journal. The dataset, original result and original 75-file evidence inventory remain unchanged.

The 12 logged ERROR events are six TLS-to-plain-HTTP parser errors and six Qdrant invalid-header errors. Adjacent unrelated quota-service requests identify a local probing pattern; the backend requests name HeadroomStreamDeck/1.3 (Antigravity local). Exact process attribution is inferred. The startup collection 404 and empty-batch capability 400 are expected. There are no unexplained benchmark non-2xx responses or application tracebacks. Latency impact is unknown and is excluded from this decision.

One native ingestion detail explains `caf03d32`: 51 physical payloads contain 50 distinct session IDs. The duplicated, non-support session has identical turns but different dates. The native logical map counts it once; graph/vector checkpoints contain both. Labeled support remains present.

Independent repricing verifies all 291 ledger attempts, including the three preflights, embedding calls and 16 native answer-budget retries. Experiment accounting is **$0.918105700**; cumulative accounting is **$10.727503350**, including **$0.073130570** of retained prior ambiguity. **$9.272496650** remains of the original $20 cap. This audit used zero provider calls. The watcher observed a process-identity change immediately after SIGTERM; historical immediate port closure remains unproved. That conservative lifecycle failure does not invalidate the settled ledger.

## Diagnostic observations, using the unchanged judge grades

| Stratum | Fresh full context | Support-only context | Paired changes |
| --- | --- | --- | --- |
| All 30 preference questions | 15/30 | 18/30 | Four wins, one loss |
| Five historical support-miss controls | 0/5 | 0/5 | No correctness changes |

`d6233ab6` belongs to both strata; there are 34 unique questions. Preference support appears in 29/30 recalls. The five miss controls still retrieve no labeled support; pruning cannot recover it. Fresh control grades differ from the historical 17/30 preferences, underscoring stochastic variation; the historical baseline remains unchanged.

This is one stochastic pass with only five discordances (exploratory paired sign-test p=0.375), plus substantial context-length changes. It does not establish a reliable retrieval improvement. Support labels are not exhaustive relevance judgments. Preference context falls from 300 records to 29 and prompt characters from 4,298,383 to 551,350, so relevance and length effects are confounded.

## Inspecting every discordance

These are editorial evidence checks, **not replacement grades**. The audit preserves every original answer and verdict.

| Question | Original change | Evidence and implication |
| --- | --- | --- |
| `32260d93`, what to watch | Wrong → correct | Full context mixes comedy, crime and drama; pruning focuses on storytelling comedy specials. Plausible context-dilution improvement. |
| `6b7dfb22`, painting inspiration | Wrong → correct | Full answer already mentions Instagram and floral painting; pruned answer adds the 30-day challenge. Some personalization improves, but the full-arm rationale overstates missing evidence. |
| `1a1907b4`, cocktails | Wrong → correct | Both answers lead with a creative Pimm’s Cup variation. The full-arm judge says this key point is missing despite its presence. The grade difference is questionable. |
| `1d4e3b97`, bike performance | Wrong → correct | Full answer explicitly mentions new drivetrain, chain/cassette and Garmin metrics; its judge claims those details are absent. Strong scoring inconsistency. |
| `afdc33df`, kitchen cleaning | Correct → wrong | Both answers mention a utensil holder and granite care. The pruned answer is less tied to the sink area, but its categorical failure is sensitive to what counts as sufficient personalization. |

Pruning also leaves four preference abstentions, including three with retrieved support (`0edc2aef`, `35a27287`, `57f827a0`). Those sessions explicitly contain the hotel-feature, language and dresser preferences, respectively. The answerer can still fail to transfer a preference into a recommendation even with only the labeled session. More context pruning alone cannot explain these failures.

A blanket top-three cutoff would reduce observed preference support coverage from 29/30 to 24/30. It would discard support for `1d4e3b97`, one apparent oracle win. Do not translate the oracle result into a lower recall limit.

## Selected next step

**Calibrate preference scoring before a product retrieval change.** Review all 60 saved preference answers, not just the five disagreements, with arm names, original verdicts and rationales hidden. Freeze evidence anchors for required preferences versus optional examples; distinguish a missing preference from failure to repeat an exact phrase. Record independent pass/fail/ambiguous assessments and disagreement reasons in a separate artifact. Keep the canonical judge/rubric and original grades unchanged during calibration. Any proposed rubric or judge change gets a separately versioned, matched replay and acceptance criteria.

The next batch is prepared as `data/sweep_runs/precision-context-20261026/calibration-blind-20261102.jsonl`, with a separate mapping and immutable packet hashes. It contains all 60 answers, questions and original references; no arm names or judge outputs. Reference evidence needs a second review stage before adjudication. This preparation makes no new model calls and does not itself establish independent calibration.

No retrieval policy is selected for shipment. After calibration, reconsider one practical evidence-selection or answer-construction condition if the corrected interpretation supports it. The graph comparison, #270, broader #31 work, new adapters, AMB/BEAM refresh and architecture changes stay parked. AutoMem #273 is merged as `fe0d5c3`; evidence #78 is merged as `cead9f4` after its refreshed clean hosted review.

Full log, ledger and integrity audits are additive files under the raw run directory. Reproduce the integrity check locally with `python data/sweep_runs/precision-context-20261026/reconcile.py`; it reads saved files and never calls providers. Original launch helpers remain in the raw evidence and at their original local paths.
