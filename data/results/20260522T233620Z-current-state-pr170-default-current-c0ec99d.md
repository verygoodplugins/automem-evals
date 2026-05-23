# Current-state recall eval - pr170-default-current-c0ec99d

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-3f2564d4e3`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `6bb6cf8c-61b2-4526-be9b-1cc0145e0881`
- `budget_counterpoint`: `d4fa18e5-b9a5-4b54-b39b-5b8c49438308`
- `budget_source`: `c7a4b2e7-0fdb-46e1-989c-d79bc6cbced5`
- `current_deploy`: `2865da90-414d-4351-ad96-939e78c0ae48`
- `current_tracker`: `f927b4df-cf9f-488c-9ddd-a68ec9d482c2`
- `expired_editor`: `58bb7a37-c029-405d-ad28-b1e73a7aec99`
- `future_editor`: `0669cfc8-6bfe-4f96-b959-edb7a76867dc`
- `gated_current_plan`: `0f6c1d55-3b66-4d84-8e9a-84763c85e1a5`
- `gated_old_plan`: `1f7093f6-9c79-43b4-a5dc-b86e72b40c76`
- `legacy_tracker`: `fa59a57e-16b1-407c-a1b3-dbf27b10e2c6`
- `old_deploy`: `7d1dac4c-ce92-47de-8490-f2b0811c623d`

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

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-3f2564d4e3","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
