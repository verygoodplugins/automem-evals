# Current-state recall eval - pr170-default-current-c032ea6

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-a77edc682d`
- current_only: `default`
- expectation: `current`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `c019ea8a-da72-41af-8ee1-b49ff2b79bd0`
- `budget_counterpoint`: `deed4900-67a8-40c0-8a9c-a0348e7c4ac6`
- `budget_source`: `e043ea65-763f-481d-8a52-2bc1d9026a4f`
- `current_deploy`: `23542f96-b611-45dd-9a4c-bc0bb69ddc76`
- `current_tracker`: `0780ac7e-ca25-4435-bcbc-7cfffc40fa01`
- `expired_editor`: `bc588dcb-9fab-4207-b969-a015239dfa92`
- `future_editor`: `86c75395-aac7-4cb5-9085-3b12f528d682`
- `gated_current_plan`: `1ffd395e-2497-496c-b2ce-0a92eb22ed3c`
- `gated_old_plan`: `8deb9133-3979-47b5-9a4a-795350294b76`
- `legacy_tracker`: `a60f09fe-d5a4-4ae1-bd94-b1334425ab85`
- `old_deploy`: `cb2eca8d-d17a-4b76-a378-6d390373e85b`

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

Params: `{"tags":["pr170-current-state-eval-a77edc682d","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-a77edc682d","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-a77edc682d","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-a77edc682d","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-a77edc682d","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-a77edc682d","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
