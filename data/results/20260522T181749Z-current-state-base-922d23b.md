# Current-state recall eval - base-922d23b

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-a2eaabf518`
- current_only: `default`
- expectation: `unfiltered`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `88c212c4-1a64-4397-aad7-71c70d9cc0bd`
- `budget_counterpoint`: `fc442962-48d2-432e-bb9e-7fa1fe286b35`
- `budget_source`: `21804d9f-e356-4c3a-91eb-11fb79e81e06`
- `current_deploy`: `26fbce39-b10f-4690-bc8a-126e1253d4f9`
- `current_tracker`: `6a25e2de-d291-404d-a52a-76d29dfc111d`
- `expired_editor`: `7fead04a-7f5b-424f-8e14-3281b547e52f`
- `future_editor`: `8cdd854d-b18b-49fc-8395-95444f8a5e7e`
- `gated_current_plan`: `3942a483-230d-409a-97ea-f2eff52d747d`
- `gated_old_plan`: `e15b2756-78d7-42ca-8f98-51ac2d9137b1`
- `legacy_tracker`: `5a1f234a-2c1f-4817-8f70-9dd6eac4b73e`
- `old_deploy`: `c98d7323-fa68-4586-aa93-5c71960407ce`

## Probe Summary

| Probe | Expect | Status | Missing | Unexpected | Suppressed | Returned keys |
|---|---|---|---|---|---:|---|
| temporal-validity | unfiltered | PASS | - | - | 0 | active_editor, expired_editor, future_editor |
| invalidated-replacement | unfiltered | PASS | - | - | 0 | legacy_tracker, current_tracker |
| evolved-replacement | unfiltered | PASS | - | - | 0 | old_deploy, current_deploy |
| replacement-respects-tag-filter | unfiltered | PASS | - | - | 0 | gated_old_plan |
| contradiction-not-suppressed | unfiltered | PASS | - | - | 0 | budget_source, budget_counterpoint |
| history-opt-out | unfiltered | PASS | - | - | 0 | active_editor, expired_editor, future_editor |

## Top Results

### temporal-validity

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval active current preference: favorite editor is Zed.
2. PR170 eval expired stale preference: favorite editor was Vim.
3. PR170 eval future preference: favorite editor will be Nova.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true}`
1. PR170 eval legacy tracker: project tracker was Jira.
2. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true}`
1. PR170 eval old deploy target: deploy target was Heroku.
2. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true}`
1. PR170 eval gated legacy billing plan: plan was Basic.

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-a2eaabf518","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
