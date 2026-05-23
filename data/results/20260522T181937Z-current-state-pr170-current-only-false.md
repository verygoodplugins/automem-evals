# Current-state recall eval - pr170-current-only-false

- endpoint: `http://localhost:8001`
- run_tag: `pr170-current-state-eval-cf6d950058`
- current_only: `false`
- expectation: `unfiltered`
- probes passed: 6/6

## Memory IDs

- `active_editor`: `a34fd75f-3858-4ae1-a088-38fd2dd52691`
- `budget_counterpoint`: `9bebf1a7-4240-4d8e-9ca5-9709878e54e8`
- `budget_source`: `06a487ff-f917-43cd-9d70-ec0034621726`
- `current_deploy`: `2a93905a-c1fd-43f2-b695-a2a0508164bb`
- `current_tracker`: `d544829d-900d-44cd-8320-4fa2733b7591`
- `expired_editor`: `c4d10684-899c-4433-bcec-4977fd2ef278`
- `future_editor`: `a5e3de13-76af-47d4-87a6-c2ff15409443`
- `gated_current_plan`: `7c0c4e0f-ae60-4e81-9b3d-4cef42e10ae6`
- `gated_old_plan`: `00dc56df-db4e-400f-a689-da1ebc6da13e`
- `legacy_tracker`: `072c231d-3ca3-4bc8-b04c-9ecb45e32950`
- `old_deploy`: `4562df9a-386d-4b93-9c3a-2ea003e1f445`

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

Params: `{"tags":["pr170-current-state-eval-cf6d950058","temporal"],"tag_mode":"all","limit":10,"query":"PR170 eval favorite editor","state_debug":true,"current_only":false}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

### invalidated-replacement

Params: `{"tags":["pr170-current-state-eval-cf6d950058","supersession"],"tag_mode":"all","limit":10,"query":"PR170 eval project tracker","state_debug":true,"current_only":false}`
1. PR170 eval legacy tracker: project tracker was Jira.
2. PR170 eval current tracker: project tracker is Linear.

### evolved-replacement

Params: `{"tags":["pr170-current-state-eval-cf6d950058","evolution"],"tag_mode":"all","limit":10,"query":"PR170 eval deploy target","state_debug":true,"current_only":false}`
1. PR170 eval old deploy target: deploy target was Heroku.
2. PR170 eval current deploy target: deploy target is Railway.

### replacement-respects-tag-filter

Params: `{"tags":["pr170-current-state-eval-cf6d950058","gated-old"],"tag_mode":"all","limit":10,"query":"PR170 eval billing plan","state_debug":true,"current_only":false}`
1. PR170 eval gated legacy billing plan: plan was Basic.

### contradiction-not-suppressed

Params: `{"tags":["pr170-current-state-eval-cf6d950058","contradiction"],"tag_mode":"all","limit":10,"query":"PR170 eval lunch budget","state_debug":true,"current_only":false}`
1. PR170 eval contradiction source: lunch budget is 100 dollars.
2. PR170 eval contradiction counterpoint: lunch budget is 200 dollars.

### history-opt-out

Params: `{"tags":["pr170-current-state-eval-cf6d950058","temporal"],"tag_mode":"all","limit":10,"current_only":false,"query":"PR170 eval favorite editor","state_debug":true}`
1. PR170 eval expired stale preference: favorite editor was Vim.
2. PR170 eval future preference: favorite editor will be Nova.
3. PR170 eval active current preference: favorite editor is Zed.

## Cleanup

- deleted_count: 11
