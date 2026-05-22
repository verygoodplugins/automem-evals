# Current-state recall eval - pr170-default-current-bca114a

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-e4a3958aff`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `8d7f3582-0dbc-4066-af47-18de1936ee32`
- `budget_counterpoint`: `68bdd26b-b133-4e07-b34c-000e556bdccc`
- `budget_source`: `9237c6e9-7797-427c-91c9-9bc5ef93ebe0`
- `current_deploy`: `faa645af-6182-48eb-b923-051fe26671e8`
- `current_tracker`: `10ecbda4-965e-4097-8ac8-7e7d50a4a3b4`
- `expired_editor`: `df7c7e48-1f76-4344-97ff-e5157a7de36f`
- `future_editor`: `84b935e4-3295-4d60-912d-5f2ee0c4c72a`
- `gated_current_plan`: `3eae602b-fd16-490c-b9fc-c73ca6af5b85`
- `gated_old_plan`: `9b23b929-8750-45c6-8ca4-c7b389a4f5c5`
- `legacy_tracker`: `174bbc7b-50de-43e4-855b-55d83e2beed6`
- `old_deploy`: `4db0d55b-1c68-443e-b614-4ef16e993c3e`

## Probe Summary

| Probe | Expect | Status | Missing | Unexpected | Suppressed | Returned keys |
|---|---|---|---|---|---:|---|
| temporal-validity | current | PASS | - | - | 2 | active_editor |
| invalidated-replacement | current | PASS | - | - | 1 | current_tracker |
| evolved-replacement | current | PASS | - | - | 1 | current_deploy |
| replacement-respects-tag-filter | current | PASS | - | - | 1 | - |
| contradiction-not-suppressed | current | PASS | - | - | 0 | budget_source, budget_counterpoint |
| history-opt-out | unfiltered | PASS | - | - | 0 | active_editor, expired_editor, future_editor |

## Top Results

### temporal-validity

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-e4a3958aff","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval future preference: favorite editor will be Nova.
2. PR170 eval expired stale preference: favorite editor was Vim.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
