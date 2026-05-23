# Current-state recall eval - pr170-default-current-c0ec99d-cleanup-fix

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-a42ca832cd`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `fb119ace-6fc8-4b4e-9e0c-f67409706470`
- `budget_counterpoint`: `c44c60b9-a1e3-4ef0-b50a-af7485c4161c`
- `budget_source`: `4c2c92c3-9793-4e0a-aa08-2eb1d9272253`
- `current_deploy`: `0f88bd2c-3f65-4c90-8e4d-5f6e0889ecaf`
- `current_tracker`: `43e7cd97-8f3d-40da-ad59-73ed420f38f3`
- `expired_editor`: `5dc13f17-4bd0-4390-8909-02fca57d8e07`
- `future_editor`: `a5095b4d-1d8e-4e64-bf78-a6d2b88584e6`
- `gated_current_plan`: `9f18bb09-a210-4284-9bc7-0e8fef1a7f65`
- `gated_old_plan`: `bd0534eb-72c9-4dc3-a5f7-2323463c9792`
- `legacy_tracker`: `2a114108-bef7-475a-820d-65e60817ad04`
- `old_deploy`: `d41ddf0b-2143-4244-b856-9213219d7419`

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

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-a42ca832cd","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
