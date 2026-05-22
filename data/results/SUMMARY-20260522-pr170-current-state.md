# PR #170 current-state recall eval

Date: 2026-05-22

Base: `922d23b` (`origin/main` at PR base)
PR behavior commit under test: `c032ea6` (`fix/recall-current-state`)

This is a PR-specific regression/acceptance experiment, not an official benchmark result.

## Targeted current-state eval

Runner: `runners/run_current_state_recall_eval.py`

The targeted runner seeds an isolated set of current/stale/future/superseded memories under a unique run tag, calls `/recall` with `state_debug=true`, scores both expected returned memories and expected suppressed memories, then deletes the seeded memories by run tag.

| Run | Endpoint code | `current_only` | Expected mode | Result | Report |
|---|---|---:|---|---:|---|
| `base-922d23b` | base | default | unfiltered | 6/6 pass | `data/results/20260522T181749Z-current-state-base-922d23b.md` |
| `pr170-current-only-false` | PR | false | unfiltered | 6/6 pass | `data/results/20260522T181937Z-current-state-pr170-current-only-false.md` |
| `pr170-default-current` | PR | default | current | 6/6 pass | `data/results/20260522T181942Z-current-state-pr170-default-current.md` |
| `pr170-default-current` | PR | default | current | 6/6 pass | `data/results/20260522T231750Z-current-state-pr170-default-current.md` |
| `pr170-default-current-c032ea6` | PR | default | current | 6/6 pass | `data/results/20260522T233256Z-current-state-pr170-default-current-c032ea6.md` |

PR default behavior suppressed the intended stale/future/superseded hits:

- `temporal-validity`: returned `active_editor`; suppressed 2 stale/future memories.
- `invalidated-replacement`: returned `current_tracker`; suppressed 1 invalidated memory.
- `evolved-replacement`: returned `current_deploy`; suppressed 1 prior state.
- `replacement-respects-tag-filter`: returned no replacement when the current replacement did not satisfy the caller tag gate; suppressed 1 prior state.
- `contradiction-not-suppressed`: returned both contradictory facts; suppressed 0.
- `history-opt-out`: explicit `current_only=false` returned active/expired/future history; suppressed 0.

## PR regression tests

Final focused server test command:

```bash
pytest tests/test_api_endpoints.py -k 'current_only or temporal_validity or invalidated or evolved or contradictions' -q
```

Result on 2026-05-23 local time: `14 passed, 84 deselected`.

The PR test coverage now includes:

- temporal validity filtering for expired and not-yet-valid memories.
- `INVALIDATED_BY` and `EVOLVED_INTO` prior-state suppression with active replacement injection.
- replacement injection respecting caller tag filters.
- `CONTRADICTS` preserving both contradictory memories.
- explicit `current_only=false` preserving historical relation states.
- vector, tag-only, and relation-expansion result filtering.

## Broad recall regression

Existing runner: `runners/compare_rulesets.py`

The broad pass used two fresh isolated matrix stacks seeded with the same `corpus_v1.embedded.jsonl` snapshot and separate generated manifests:

- Base stack: `http://localhost:8051`, manifest `data/seed_memories/corpus_v1-pr170-broad-base.manifest.json`
- PR stack: `http://localhost:8061`, manifest `data/seed_memories/corpus_v1-pr170-broad-pr.manifest.json`

Command shape:

```bash
python3 runners/compare_rulesets.py \
  --endpoint <endpoint> \
  --token test-token \
  --rulesets baseline_v1 bare_tag_1m_v2 \
  --scenarios session_start_v1 \
  --manifest <manifest>
```

Results were identical between base and PR across all 10 `session_start_v1` scenarios for both `baseline_v1` and `bare_tag_1m_v2`.

- Base report: `data/results/20260522-202507-comparison.md`
- PR report: `data/results/20260522-202511-comparison.md`

## Takeaway

Targeted current-state behavior improved: stale, future, invalidated, and evolved memories are removed from default recall while explicit history mode still works. The broad recall benchmark was unchanged between base and PR, so it remains useful as a collateral-damage smoke test but is not sufficient by itself because it mostly measures expected-hit presence and rank rather than stale-hit absence.
