# Veracium / Ground Truth First

Experimental AutoMem evaluation track; status **not_scored** (2026-10-09).
Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.
Tracker: [issue #62](https://github.com/verygoodplugins/automem-evals/issues/62).

## Evidence and scope

[Ground Truth First, arXiv:2607.21962v1](https://arxiv.org/abs/2607.21962v1)
(24 July 2026) describes approximately 380 questions across 15 types,
fact-validity intervals, sent/received trust, injection probes, and as-of sets.
The short corpus has 275 questions; the tenure corpus has 108 questions with
week-3/6/9 checkpoints. Preserve these distinct denominators.

**Paper baselines, never AutoMem scores:** early-chapter curated-map accuracy
falls from 96.3% to 72.2% with tenure; graph accuracy reaches 90.4%.
Write quality correlates with downstream failures; injection resistance follows
preserved provenance boundaries. These observations motivate separate write,
retrieval, answer, and injection measurements rather than a pooled QA score.
[Paper sections 3 and 5](https://arxiv.org/html/2607.21962v1).

## Release and local feasibility

The paper's [reproducibility statement](https://arxiv.org/html/2607.21962v1)
says the study package (generator, harness, corpora, verdicts, logs) is in
preparation, pending an immutable release and archived DOI. The public
[Veracium repository](https://github.com/veracium-ai/Veracium) is the library.
At revision `f7a1a42159b1027b75e8a0c08e7cc4874b92e1b2` (MIT, version 0.26.1),
its `tests/eval/scenarios.json` contains four acceptance scenarios, seven
events, and five probes: supersession, injection, abstention, grounded inference.
It does not supply the paper's longitudinal corpus, validity oracle, or generator.
The public organization exposes no separate study repository.

The acceptance harness imports and validates those probes locally. Execution
fails before the first LLM call with `StoreVersionError: unsupported-sqlite`:
SQLite 3.53.4 is not an upstream-qualified build identity. The offline semantic
recall gate has one passing artifact check and four failures with the same cause.
No upstream runtime guard was bypassed. See [captured verification](veracium-verification.md).

The conditional runnable-harness requirement is therefore unmet: no
`runners/veracium/`, invented corpus, AutoMem smoke score, or leaderboard result
is delivered. The five acceptance probes cannot substitute for the study.
An AutoMem adapter remains gated on official study artifacts; fixing the local
SQLite compatibility alone does not unblock a faithful longitudinal run.

## Proposed AutoMem mapping

| Instrument construct | Adapter treatment | Required observation |
| --- | --- | --- |
| Fact validity interval | Map source start/end to `t_valid`/`t_invalid`; retain narrative timestamp and original interval in metadata. | Verify stored bounds via `/memory/<id>`; test exact boundary semantics, open-ended intervals, and retained historical facts. |
| As-of question | Temporal `/recall` with narrative `as_of` and `end` bounds; replay only events available by that checkpoint. | No future evidence; correct current/historical view at week 3, 6, and 9. `end` bounds observation time and cannot alone enforce fact validity. |
| Changed fact | Replacement uses `supersedes_memory_id`; lifecycle edge is old → new (`INVALIDATED_BY` for correction, `EVOLVED_INTO` for evolution). | Verify causal edge and old node's `t_invalid`; use narrative change time, never ingest wall-clock time. |
| Sent versus received | Host-assigned `metadata` records source/event ID, channel, author, direction, trust, and source date. User-sent mail and third-party-received mail remain distinct. | Content cannot forge provenance; preserve claimant attribution through extraction, deduplication, summaries, and graph expansion. |
| Injection probe | Audit write-time provenance checks and promotion/quarantine behavior before retrieval. Store received assertions as attributed claims. | An incoming claim must not overwrite a trusted user fact or become an asserted obligation. Metadata labels alone are not an enforced trust boundary; report AutoMem capability gaps. |
| Write fidelity | Audit the complete stored bank against source fact manifests, including interval and provenance fidelity, before asking questions. | Separate supported-fact coverage and unsupported promotions from retrieval misses and answer errors; do not seed gold answers as memories. |

These are adapter requirements, not claims that every server feature already
exists. Confirm the served API and returned records before wiring parameters;
explicitly report unsupported historical/supersession semantics.

## Acceptance criteria after release

- [ ] Pin official study code/data/scorer SHA or DOI, checksums, licenses,
      generator seeds, question types, and checkpoint/event ordering.
- [ ] Add a stdlib, local-endpoint-only `runners/veracium/` adapter. Reject
      non-loopback URLs and redirected writes; isolate run/user tags and clean
      up only manifested run IDs, without resetting the existing corpus.
- [ ] Preserve official loader, gold labels, answerer/judge prompts and versions,
      replicate identifiers, retrieval budget, and exclusions.
- [ ] Test validity boundaries, as-of leakage, historical retrieval, lifecycle
      direction, sent/received provenance, and injection promotion failures.
- [ ] Run a small real official subset covering changed/current/historical
      facts, sent/received mail, injection, and both horizons. Record exact
      commands, source SHA, selected IDs, request/response artifacts, and cleanup.
- [ ] Report write fidelity separately from support retrieval, answer accuracy,
      injection assertions, and abstention, sliced by type/checkpoint with counts.
- [ ] Follow [maturation.md](maturation.md): report `cold`, `matured`, and any
      `matured-full` separately. Keep unavailable maturation explicitly blocked.
- [ ] If answerer/judge access fails (including `429 credit_balance_exhausted`
      observed in PR #61), use `not_scored`, null rates, and exact errors. Never
      convert unavailable judgments to zero accuracy or fabricate scores.
- [ ] Pass both repository unittest discovery commands and capture their output.

## Deduplication and follow-ups

Before creating the tracker, all-state issue searches and these neighbors were
checked: #50 StateMemBench (current/superseded outcomes), #51 MemTrace (evidence
use), #57 A-TMA (state views/ghost memory), #22 Memora/FAMA (forgetting-aware
accuracy), #31 ForgetEval (mutation controls), #53 MERIT (cost-aware actions),
and PR #61 EvalMem (operation diagnostics). None covers this combined
longitudinal validity/provenance/injection instrument. PR #61 was **OPEN** at
inspection, rather than merged as described in the request.

Follow up separately on [DynamicMem, arXiv:2606.22877](https://arxiv.org/abs/2606.22877)
(15-month multi-app profiles/checkpoints) and
[MEMPROBE v1, arXiv:2606.24595v1](https://arxiv.org/abs/2606.24595v1)
(hidden user-state recovery under full-store/top-k access). The latter is renamed
[MemAudit in v3](https://arxiv.org/abs/2606.24595v3); track by arXiv ID to avoid
duplicate issues. No dedicated tracker for either was found; DynamicMem is
mentioned in #51. Neither replaces the Veracium study artifacts.
