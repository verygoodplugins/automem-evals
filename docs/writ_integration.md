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

## Adapter mapping (Phase 1, drift only)

| writ method | AutoMem implementation |
| --- | --- |
| `init()` | `GET /health` smoke |
| `processSession()` | Per user message: regex-extract canonical fact values (employer, base_salary, relationship_status, …); `POST /memory` with the run tag, fact tags, and `metadata.writ_fact_values` map. |
| `probe()` | `GET /recall?tags=<runTag>&limit=50&sort=recent`. Sort recalled items by session timestamp; `answer` concatenates raw content + `[facts: factId=value]` so structured-recall scoring catches canonical strings the user never typed verbatim ("independent consultant"). |
| `getHistory(factId)` | Walk the in-memory `factHistory` populated during `processSession`. |
| `getStateAsOf(factId, ts)` | Linear scan of the same history; returns the latest value with `as_of <= ts`. |
| `getProvenance()` | Returns `null` — Phase 3. |
| `reset()` | `DELETE /memory/<id>` for every memory we stored under this run, then rotate the run tag. **Cheap** (no `docker compose down`); writ calls `reset()` before every scenario. |
| `teardown()` | Same as `reset()`. |

### Why tag-only recall

writ's drift probes are meta-questions ("Can you remind me of my employment
history this year?"). AutoMem's vector ranker drops sessions below a similarity
threshold even when the tag gate matches, so semantic-mode recall returned 0
sessions on 2 of 5 drift scenarios. The adapter uses `tags: [runTag]` with
`sort: "recent"` and re-sorts by writ's `session_id` client-side — the run tag
is already a unique partition.

### Why fact extraction lives in the adapter

writ's `MemoryAdapter` is told the value of a fact via `getHistory(factId)`.
Without explicit fact extraction the only option is to dump raw user messages,
which scores well for `recall_correct` (substring match against
`required_elements`) but fails `drift_detected` (`matchesCurrentValue` needs the
*current* value, not the message that set it). The drift-only `FACT_EXTRACTORS`
table covers the five drift scenarios: employer, title, base_salary,
bonus_target, signing_bonus, relationship_status, partner_name,
living_arrangement, home_city, neighborhood, blood_pressure_medication,
diabetes_medication, health_conditions, lisinopril_side_effect.

Other categories will need their own extractors (or, eventually, an LLM
extraction stage — out of scope for Phase 1).

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

- **Drift-only fact extractors.** Other categories (temporal, update, lifecycle)
  will need additional extractors or an LLM extraction pass.
- **Provenance.** `getProvenance()` returns `null`. Provenance category will
  always score 0 until we model `metadata.source` + association chains.
- **`update_fidelity` ceiling.** Limited by writ's narrative-string matching;
  not an AutoMem failure.
- **Server consistency.** Vector indexing for newly-stored memories is
  occasionally slow; `probe()` uses a tag-only fallback to avoid empty results.

## Files of interest

- `runners/run_writ.py` — Python driver
- `runners/writ/automem-adapter/automem.ts` — adapter source
- `runners/writ/automem-adapter/run.ts` — TypeScript entry point
- `third_party/writ/src/evaluator.ts` — read this to understand how scores are
  computed (especially `checkStructuredRecall`, `checkUpdateFidelity`,
  `matchesCurrentValue`).
