# Current-state recall eval - pr170-default-current

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-3c8a0ef775`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `6e8da869-fe17-42fa-8f38-b8215e48297a`
- `budget_counterpoint`: `5428751a-1b7c-401b-a15e-8b1a41a776ef`
- `budget_source`: `3e28a9fe-863d-410f-914e-4c87990cc83b`
- `current_deploy`: `538f528f-fa32-4091-8495-a26b340bbbec`
- `current_tracker`: `f3c6b685-a394-4d27-92ec-10392678a48c`
- `expired_editor`: `593b8cdb-6009-4a5a-9b40-b4e7d5d281ad`
- `future_editor`: `156b9a4d-8c80-461f-b435-95d226534e4a`
- `gated_current_plan`: `e4f6a505-f0e8-4036-bb2e-6df3cdc3ebb0`
- `gated_old_plan`: `4c3279a0-13cb-499b-8c9d-a319f27fd832`
- `legacy_tracker`: `0a3d0f29-61bd-4656-b1c7-bedd7fc11f8a`
- `old_deploy`: `67b7a46d-38df-4d3f-bc32-fc861b9d2e8b`

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

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-3c8a0ef775","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval future preference: favorite editor will be Nova.
2. PR170 eval expired stale preference: favorite editor was Vim.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
