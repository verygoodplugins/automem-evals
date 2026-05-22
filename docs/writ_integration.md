# WRIT integration — write-integrity benchmark

[writ](https://github.com/markmhendrickson/writ) is a TypeScript benchmark that
tests whether stored facts survive multi-session writes (drift, temporal,
provenance, constraint, entity, lifecycle, ...). It is **complementary** to the
recall-quality experiments in this repo: writ probes how well a memory backend
preserves and updates *what was written*, while `runners/compare_rulesets.py`
probes how well `/recall` parameters surface what's already stored.

This integration is experimental. Official benchmark numbers (LoCoMo,
LongMemEval) still live in the `automem` repo per `docs/REPO_BOUNDARY.md`.

## What runs

```
runners/run_writ.py        — Python driver (stdlib only)
  └─ copies →  third_party/writ/src/adapters/automem.ts
  └─ copies →  third_party/writ/run_automem.ts
  └─ shells out to  npx tsx run_automem.ts ...

runners/writ/automem-adapter/
  ├─ automem.ts            — MemoryAdapter implementation against AutoMem HTTP
  └─ run.ts                — entry point (re-uses writ's exported runBenchmark)
```

The submodule at `third_party/writ` stays untouched on disk; the driver copies
the adapter + entry point in at run time. Same pattern as `runners/run_beam.py`
+ `runners/beam_shim*.py`.

## One-time setup

```bash
git submodule update --init --recursive    # vendors writ at the pinned commit
cd ../automem && docker compose up -d      # AutoMem stack on :8001
```

The driver will `npm install` inside `third_party/writ` on first run.

## Running

```bash
# Single adapter
python3 runners/run_writ.py --adapter automem  --scenarios drift
python3 runners/run_writ.py --adapter baseline --scenarios drift

# A/B comparison (writes a markdown diff into the run dir)
python3 runners/run_writ.py --compare automem baseline --scenarios drift
```

Other flags: `--modes`, `--endpoint`, `--token`, `--label`. `--scenarios` can be
any writ category (`drift`, `temporal`, `update`, `lifecycle`, `provenance`, ...)
or `all`.

Reports land in `data/results/writ/<timestamp>-<scenarios>[-<label>]/`:
- `<adapter>/writ-<adapter>-<ms>.json` — raw report
- `<adapter>/writ-<adapter>-<ms>.md`  — rendered scorecard
- `comparison-<a>-vs-<b>.md`            — side-by-side diff (only with `--compare`)

## Adapter mapping

| writ method | AutoMem implementation |
| --- | --- |
| `init()` | `GET /health` smoke |
| `processSession()` | Stores every user message under the unique run tag. Metadata preserves session id, message index, role, timestamp, source-authority hint, raw content, extracted fact ids, extracted values, and observation records. |
| `probe()` | Queries AutoMem with prompt + run tag, then answers from the local observation index when it can resolve current, history, temporal, or provenance intent. History prompts can fall back to run-tag chronological recall. Unresolved or sensitive prompts abstain. |
| `getHistory(factId)` | Resolves `factId` by normalized token overlap against the observation index and returns chronological values. |
| `getStateAsOf(factId, ts)` | Replays the resolved fact history by timestamp and returns the latest value with `as_of <= ts`. |
| `getProvenance(factId)` | Returns source session/message and an update chain when the resolver identifies the fact source. This is partial local support, not full provenance modeling. |
| `reset()` | `DELETE /memory/<id>` for every memory we stored under this run, then rotate the run tag. **Cheap** (no `docker compose down`); writ calls `reset()` before every scenario. |
| `teardown()` | Same as `reset()`. |

### PR scope

The adapter should be a fair wrapper around AutoMem behavior, not a WRIT answer
key. It must not use `scenario_id`, `ground_truth.current_value`,
`ground_truth.value_history`, or rubric strings to generate answers. The allowed
inputs are WRIT's adapter contract: session messages, timestamps, roles, probe
prompt, `factId` parameters, and AutoMem-returned memory metadata.

This PR improves local diagnostics by broadening ingestion and adding a general
in-memory observation index. It also makes comparison reports easier to read by
separating raw WRIT metrics from local interpretation labels. It does not change
upstream WRIT, the raw WRIT JSON schema, or AutoMem core behavior.

Remaining lifecycle/provenance/category failures are not automatically AutoMem
core bugs. They are follow-up signals for adapter capability layers unless they
persist after the adapter implements the corresponding behavior generally and
declares that capability honestly.

### Why the observation index exists

writ's `MemoryAdapter` methods ask for structured behavior (`getHistory`,
`getStateAsOf`, `getProvenance`) even though AutoMem stores memories through a
general HTTP API. The adapter therefore keeps a local observation index while it
stores each user message. Extraction is intentionally generic: drift facts are
one extractor family, alongside broader observations for money amounts,
addresses, dates, people, organizations, task states, preferences,
constraints, lifecycle words, retractions, contacts, travel, and raw messages.

`factId` resolution uses normalized token overlap between the requested fact,
observation labels, extracted values, and message terms. This is still a local
adapter policy, but it is not keyed to WRIT scenario ids or expected answers.

### Why reports have interpretation overlays

The comparison markdown preserves raw WRIT aggregate scores. Local sections add
human-readable interpretation for this repo's diagnostic use:

- `drift_rate` and `hallucination_rate` are labeled lower-is-better.
- Metrics with no applicable per-scenario score are labeled not exercised in
  that run, instead of being treated as product failures.
- Drift history prompts get a history-aware stale-memory overlay: raw
  `update_fidelity` is unchanged, but stale failures on history-preservation
  probes are counted separately when recall and drift detection both passed.

## Current results — drift category

```
                          automem   baseline   delta
recall_accuracy            100.0%      0.0%   +100.0pp
update_fidelity             20.0%      0.0%    +20.0pp
detectability              100.0%      0.0%   +100.0pp
drift_rate                   0.0%    100.0%   -100.0pp
hallucination_rate           0.0%      0.0%      0.0pp
abstention_quality         100.0%      0.0%   +100.0pp
```

5 of 5 drift scenarios pass `recall_correct` against AutoMem; baseline scores 0.

`update_fidelity` stays low because writ's evaluator does a literal substring
check against `ground_truth.current_value`, which is written as a human-style
narrative ("losartan 50mg (only current medication)", "$115,000 base + $5,000
bonus target") not present in any user message. drift-001 — where the canonical
extracted value matches verbatim — passes; the rest score 0 on this one metric.
Closing the gap requires an LLM-style narrative answer, which is out of scope.

## Known gaps

- **Partial provenance.** The adapter can return source session/message for
  resolved observations, but it does not yet model full source authority,
  association chains, or conflict resolution.
- **Lifecycle and policy categories.** Lifecycle, source authority, trust
  hierarchy, certification, and constraint categories need explicit generalized
  adapter policy before their failures should be read as AutoMem core behavior.
- **`update_fidelity` in history prompts.** Some drift probes ask for history.
  Old values are expected in those answers, so the local comparison report adds
  a history-aware stale-memory overlay while leaving raw WRIT scores unchanged.
- **Server consistency.** Vector indexing for newly-stored memories is
  occasionally slow; `probe()` uses run-tag recall fallbacks to avoid empty
  results when direct prompt recall misses fresh writes.

## Files of interest

- `runners/run_writ.py` — Python driver
- `runners/writ/automem-adapter/automem.ts` — adapter source
- `runners/writ/automem-adapter/run.ts` — TypeScript entry point
- `third_party/writ/src/evaluator.ts` — read this to understand how scores are
  computed (especially `checkStructuredRecall`, `checkUpdateFidelity`,
  `matchesCurrentValue`).
