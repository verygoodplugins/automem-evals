# Inline obsolete-content suppression — 2026-10-26

Follow-up to the [frozen post-merge baseline](session_20261022_postmerge_baseline.md), scoped to the inline relation leak in [#31](https://github.com/verygoodplugins/automem-evals/issues/31).

The prerequisite PRs landed in dependency order: evals #71, AutoMem #272, evals #73 into #72, then evals #72. AutoMem #273 is the single active product change. This report's matched replay is the single active evaluation batch.

## Change and contract

Current-state recall already suppressed obsolete top-level results. An active neighbor could still expose an expired or superseded memory through `results[].relations[].memory.content` or `.summary`. Relation summaries omit lifecycle fields, and graph/vector hydration paths did not apply the top-level state checks to those targets.

[AutoMem #273](https://github.com/verygoodplugins/automem/pull/273) adds one batched graph lookup after final relation hydration. Current mode exposes inline payloads only when the graph target is present, temporally valid, unarchived, and lacks an active `INVALIDATED_BY` / `EVOLVED_INTO` successor. Other targets retain only their ID, preserving relationship type, strength, kind and provenance. Missing targets or a failed verification lookup also retain only the ID. Active neighbors keep their existing payloads. Explicit `state_mode=history` / `current_only=false` retains historical inline content.

This changes recall serialization. It does not migrate or delete stored memories, add an atomic supersede API, change retrieval ranking, or address enrichment race AutoMem #270.

## Verification status

The new regression test failed before the fix with obsolete content still present in the inline payload. After the fix:

- 60 endpoint cases cover graph/vector results, content/summary serialization, expired/future/archived targets, both suppressing edge types, and both explicit history opt-ins.
- Two focused checks preserve provenance when a target is missing or the graph lookup fails.
- Full non-benchmark suite: **892 passed, 12 skipped**, two pre-existing `utcnow` deprecation warnings in health-monitor tests.
- Changed Python files pass Black, Isort and Flake8.
- Local Codex review (`gpt-6.1-sol`, medium, one pass) found no actionable regressions.

The matched real FalkorDB/Qdrant replay completed with the same inputs and no query errors:

| Check | Frozen baseline | Fix candidate |
| --- | ---: | ---: |
| Full ForgetEval | 234/385 | 234/385 |
| Top-level graph probes | 10/10 | 10/10 |
| Complete-response graph probes | 5/10 | **10/10** |
| Execution errors | 0 | 0 |

All 385 paired inputs match exactly: 234 unchanged passes and 151 unchanged failures; no newly failing standard cases. Only `supersede-0` through `supersede-4` changed, all from fail to pass. Those five fixtures previously exposed `retired-N` content through an active neighbor's inline relation. Purge fixtures remain unchanged. This is a correctness improvement with stable top-level scores.

[Curated result and evidence manifest](../data/results/inline-obsolete-20261026/SUMMARY.md) link to the raw per-case comparison, complete responses, command ledger, model hashes, health snapshots and cleanup records. A separate real-store contract probe also passed all four checks: current mode retains the active inline payload and strips the expired payload to its ID; history mode retains both payloads. Candidate logs contain no state-verification failures, AutoMem query exceptions or tracebacks. Two unrelated malformed transport requests produced Werkzeug HTTP 400 entries; neither appears in a suite case, and their caller is unknown. Both the matched runs and the extra contract stack were cleaned up completely.

## Frozen comparison

- Baseline server: `3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876`.
- Candidate server: `f5d88f14393f51ddbc6027ecabcf316090b8d445`.
- Candidate parent: `f47e1896764b02f31cd6bb2fbc8a26cc35a219ce`; server sources are identical to the baseline before this fix (the intervening merge only published benchmark metadata).
- Fresh ingestion into separate disposable stores. Cold local BGE-small-en-v1.5, 384 dimensions; enrichment, JIT and consolidation disabled.
- Same pinned ForgetEval adapter and Lethe inputs as the original free baseline. Exact hashes, commands, health and per-case envelopes accompany the run artifacts.
- Full 385-case diagnostic plus the ten graph residual probes. Score the complete JSON envelope as well as top-level results.

The original paid campaign remains closed at **$9.809397650 accounted** of its $20 cap. This follow-up uses no paid APIs and does not reset that accounting. Official LongMemEval / LoCoMo scores remain the frozen baseline; this is an exploratory correctness verification, not a new answer-quality claim.

## Next action

The focused fix is verified. Review and merge #273, then start the controlled precision experiment. Keep #31 open for its broader deferred control-plane work; the inline leak is the only part addressed here. After this fix lands, proceed to one controlled precision experiment, then the matched graph-on/graph-off comparison. AutoMem #270, atomic operations, adapter expansion, AMB/BEAM refresh, maturation and architecture work remain parked.

## Review record

Product branch `fix/inline-obsolete-relations`; verified PR head `f5d88f14393f51ddbc6027ecabcf316090b8d445`. Four changed files, **150 changed lines**; size gate passed. Product implementation is limited to the recall serializer, shared test fake, endpoint regressions, and API contract documentation.

Local review ran once with Codex `gpt-6.1-sol` / medium and found no actionable regressions. Hosted GitHub Codex automatically reviewed the same head and settled clean via a current-head **👍 reaction** at `2026-10-26T01:32:08Z`; no inline threads. All six required checks passed: pre-commit, Node tests, Python 3.10/3.11/3.12 tests, and semantic PR title. No review-request comments, remediation pushes, budget resets, quota skips, or residual findings were needed. Convergence: clean. Tier A used the shipped babysit scripts; implementation and triage stayed in the parent session; no Tier B fix executor was required. Local/full-suite runtime was 4.89 seconds; other phase timings were not measured.

The new product PR remains open for review and merge. It has not been merged automatically.
