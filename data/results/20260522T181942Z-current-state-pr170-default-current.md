# Current-state recall eval - pr170-default-current

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-35a445d0e8`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `12f98919-23f9-4ba6-bc35-b938f24948a7`
- `budget_counterpoint`: `f50d6f70-a90f-43c4-96ef-d07f7884ec1c`
- `budget_source`: `a06f465c-5c56-4c03-acd2-4401f4887caf`
- `current_deploy`: `0c2b18af-1dc5-4ed8-be2a-a4751ed04331`
- `current_tracker`: `bc80c397-bc11-4d22-806c-2041aae3bbe9`
- `expired_editor`: `20006e2e-3fcf-4c71-8413-eb62875970dc`
- `future_editor`: `d0c97b47-1cbc-4b10-995a-1908098d2d3c`
- `gated_current_plan`: `80815c53-b238-4012-a3f2-dbd3202ba465`
- `gated_old_plan`: `60a031d4-6721-4353-96e0-01cc1ec1ee5c`
- `legacy_tracker`: `88bb9d86-ea3a-46ff-a2a8-13d93b9dc7d0`
- `old_deploy`: `26ee31c1-388f-4bb0-b06f-c78de6925636`

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

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-35a445d0e8","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
