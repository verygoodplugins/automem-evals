# A-TMA / LTP — state-aware ghost-memory evaluation

## Decision

Track A-TMA and its LoCoMo Temporal Plus (LTP) benchmark as a distinct
state-view evaluation.  It is related to, but must not be folded into:

- #31, which evaluates explicit control-plane forgetting operations;
- #22/#23, which track Memora/FAMA invalid-memory behavior;
- #50, which tests current-versus-superseded outcomes in StateMemBench; and
- #51, which diagnoses evidence use in MemTrace.

The separate contribution here is **ghost memory**: retained old, current, and
transition records become harmful when retrieval or QA mixes their roles.  A-TMA
therefore separates bank maintenance, retrieval, and answer-time resolution.

Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.

## Release status — blocked on official artifacts

**Decision as of 2026-10-04: do not add an adapter, synthetic substitute, or
AutoMem score.** The manuscript is public, but the official LTP replay data,
questions/gold answers, loader, and scorer needed for a faithful run are not.

| Checked source | Finding on 2026-10-04 |
| --- | --- |
| [arXiv record v2](https://arxiv.org/abs/2607.01935v2) | Public manuscript only. It was submitted 2026-07-02 and revised 2026-07-08; the record offers HTML, PDF, and source, but no author data/code URL or dataset DOI. |
| [arXiv HTML v2](https://arxiv.org/html/2607.01935v2) / PDF | The paper specifies LTP as 10 profiles and 800 QA probes, but supplies no LTP download, repository, loader, evaluator, artifact revision, checksum, or license. The only project GitHub link in the rendered paper is the cited Graphiti host dependency, not A-TMA/LTP code. |
| [Yixuan Tang's publications page](https://www.comp.nus.edu.sg/~yixuan/publications/) | Lists A-TMA as a 2026 preprint with a paper link and BibTeX; unlike entries that expose a separate `Code` link, it exposes no A-TMA/LTP code or dataset link. |
| GitHub repository search | Exact-title and exact `LoCoMo Temporal Plus` searches returned no official repository. Do not treat unrelated repositories matching the acronym `TMA` as an author release. |
| Hugging Face Hub API | Dataset search for `LoCoMo Temporal Plus` and model search for `A-TMA` each returned an empty result set; there is no official dataset/model revision to pin. |

The paper calls LTP a conflict-heavy LoCoMo extension, but public LoCoMo material
cannot substitute for LTP's paired old/current state units, transition records,
probe splits, gold answers, or benchmark-specific scoring.  Revisit only when
the authors publish all of the following: official data, replay/ingestion order,
question and gold-answer format, scorer, immutable revision/checksum, and license.

The paper figures remain **paper baselines, never AutoMem scores**: it reports
Graphiti + A-TMA gaining 0.240 absolute conflict accuracy on LTP, and temporal
F1 on LoCoMo rising from 0.0295 to 0.1705.  Those host-specific results must not
be relabeled as an AutoMem result.

## Why an AutoMem track is still useful

A-TMA's proposed overlay preserves superseded state, builds a query-view-specific
evidence packet, and labels evidence as `current`, `historical`, or `transition`
before QA. That maps to AutoMem lifecycle primitives, but it also identifies a
read-side capability gap: ordinary recall does not yet return an explicit
state-labelled evidence packet.

### Mapping to AutoMem

| A-TMA construct | AutoMem adapter treatment | Required assertion |
| --- | --- | --- |
| Superseded fact | Store the replacement with `supersedes_memory_id=<old-id>`. This must set the old record's `t_invalid` while retaining the old record for audit/history. | A current-state recall suppresses the old record and returns the replacement. |
| Correction provenance | Use `INVALIDATED_BY`, always **old -> new**. | `state_debug` identifies the old record as suppressed by the causal edge. |
| Evolution rather than correction | Use `EVOLVED_INTO`, always **old -> new**. | The old record is suppressed in current-only recall without deleting historical provenance. |
| Current view | Use `current_only=true`, plus the source's narrative `as_of` boundary when supplied. | Returned evidence contains the state operative at the query time, without future leakage. |
| Historical view | Retain the old record and retrieve with `current_only=false`; constrain the result to the requested narrative point. | The historical target remains discoverable rather than being replaced by its successor. |
| Transition view | Follow the ordered old-to-new `INVALIDATED_BY`/`EVOLVED_INTO` chain and preserve timestamps/event metadata. | The packet contains the contiguous chronological chain, not only its newest endpoint. |

Lifecycle direction is a correctness condition, not metadata decoration. Reversing
either edge hides the new fact under current-only recall and revives stale state.
Use `supersedes_memory_id` rather than hand-writing the lifecycle relation where
possible, then verify both `t_invalid` and the old-to-new edge direction.

### Candidate AutoMem product issue

The evaluation should open a **separate `verygoodplugins/automem` issue** once
the exact recall envelope is designed: return a state-labelled evidence packet
for a requested `current`, `historical`, or `transition` view. A packet should
include the requested view/as-of boundary, each memory id and state role, the
old-to-new lifecycle path for transitions, and the suppression explanation for
excluded current-only records. This tracker does not claim that such an output
exists today; it names it as a candidate read-side feature.

## Decoupled scoring plan (after an official release)

Preserve LTP's official splits, gold labels, scoring implementation, and
denominators. Do not convert paper descriptions into locally invented cases.
Every probe has a source-provided state view and is scored at all three levels
where the artifact permits it.

| Level | Question | Measures and failure attribution |
| --- | --- | --- |
| 1. Bank maintenance | Did ingestion represent the state change correctly? | State-unit write success; retained old/current/transition records; correct `t_invalid`; directed old-to-new lifecycle edge; role/provenance metadata; and no accidental deletion or merge. A failure here is a **bank failure** even if a later answer happens to be correct. |
| 2. Retrieval | Did recall return the evidence required for the requested view? | Target-support recall; stale-state leakage for `current`; historical-target recall for `historical`; ordered complete chain recall for `transition`; and as-of leakage. A failure here is a **retrieval failure** only when Level 1 passed. |
| 3. Answer-time resolution | Given a state-labelled, source-valid packet, did the answer use the correct state? | Official answer correctness plus wrong-state selection (current substituted for historical, historical substituted for current, or endpoint substituted for transition). A failure here is an **answer-time failure** only when Levels 1 and 2 supplied sufficient evidence. |

Report the cross-level contingency table, not just final QA accuracy: bank-pass /
retrieval-pass /
answer-pass, with source-provided current, historical, and transition slices.
This keeps a lucky correct answer from concealing a malformed bank and keeps a
missing record from being blamed on QA. Record returned memory IDs, state roles,
lifecycle paths, requested view, as-of boundary, answer, and official judge
outcome for every scored probe.

## Required run modes and controls

Follow [the maturation contract](maturation.md) for every curated result:

- `cold` is immediate-ingest retrieval and remains the leaderboard-comparable
  figure.
- `matured` drains enrichment and runs the frozen narrative-time maintenance
  profile with decay/forget off.
- `matured-full` is reported separately if decay/forget is enabled; it is never
  pooled with the other modes.

All modes must honor the official question's narrative `as_of` boundary. The
matured run must not consolidate from future facts, and the same frozen profile,
models, seed, prompt, retrieval budget, artifact revision, and local-only endpoint
rule must be used across state views. Until the repository's narrative-clock
`/consolidate` dependency is implemented, label any possible run `cold` and record
`matured: blocked`; do not call a cold run mature.

## Acceptance on release

- [ ] Pin the official code/data revision, checksum, license, loader schema, and scorer contract.
- [ ] Add `runners/atma_ltp/` only after that pin, with unit tests for lifecycle direction, `t_invalid`, current/historical retrieval modes, chronological transition chains, isolation, and rejection of non-local endpoints.
- [ ] Run a small **real official** smoke subset that covers every available state view; save the exact command, source revision, and raw artifact.
- [ ] Produce separate bank, retrieval, and answer-time metrics for `cold` and `matured` (and separately labelled `matured-full` if run).
- [ ] Never fabricate LTP-like data or publish an AutoMem score before the official artifacts and smoke run exist.

## Sources

- [A-TMA arXiv record v2](https://arxiv.org/abs/2607.01935v2)
- [A-TMA rendered HTML v2](https://arxiv.org/html/2607.01935v2)
- [Yixuan Tang — publications](https://www.comp.nus.edu.sg/~yixuan/publications/)
- [Repository maturation contract](maturation.md)
