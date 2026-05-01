# Production Stage 1 Cleanup Execute

- Run timestamp: `20260501-124737`
- Endpoint: production AutoMem endpoint from `AUTOMEM_ENDPOINT`
- Artifact directory: `data/sweep_runs/20260501-124737-prod-stage1-execute`
- Mode: execute, one filter per process, with full-record backup before each delete pass
- Credentials were supplied from environment variables and are intentionally omitted.

## Outcome

- Deleted records: `3158`
- Health before: `11046` memories / `11046` vectors, `synced`
- Health after: `7894` memories / `7894` vectors, `synced`
- Net health delta: `-3152` memories. This differs from deletes by `6` because production remained live during the run.
- Delete errors: `0`
- Preserve regressions from sweep runner: `0` for every filter
- Recall preserve regressions: `0`; every after-filter recall comparison exited `0`

## Filters Executed

| Filter | Matched | Deleted | Backup lines | Backup |
|---|---:|---:|---:|---|
| `SWEEP-LOCOMO-BENCHMARK` | 953 | 953 | 953 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-LOCOMO-BENCHMARK/SWEEP-LOCOMO-BENCHMARK.backup.jsonl` |
| `SWEEP-BUILD-RESULTS` | 526 | 526 | 526 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-BUILD-RESULTS/SWEEP-BUILD-RESULTS.backup.jsonl` |
| `SWEEP-TEST-RESULTS` | 542 | 542 | 542 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-TEST-RESULTS/SWEEP-TEST-RESULTS.backup.jsonl` |
| `SWEEP-MOLTBOOK-ENGAGEMENT-PINGS` | 328 | 328 | 328 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-MOLTBOOK-ENGAGEMENT-PINGS/SWEEP-MOLTBOOK-ENGAGEMENT-PINGS.backup.jsonl` |
| `SWEEP-TWITTER-ENGAGEMENT-PINGS` | 150 | 150 | 150 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-TWITTER-ENGAGEMENT-PINGS/SWEEP-TWITTER-ENGAGEMENT-PINGS.backup.jsonl` |
| `SWEEP-STARTED-SESSION` | 132 | 132 | 132 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-STARTED-SESSION/SWEEP-STARTED-SESSION.backup.jsonl` |
| `SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY` | 527 | 527 | 527 | `data/sweep_runs/20260501-124737-prod-stage1-execute/execute-SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY/SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY.backup.jsonl` |

## Preserve Counts

| Class | Before | After |
|---|---:|---:|
| autojack-blog published artifacts | 52 | 52 |
| user preferences | 49 | 49 |
| deployments | 376 | 376 |
| bugfixes | 69 | 69 |

## Recall Checks

- Baseline recall summary: `data/sweep_runs/20260501-124737-prod-stage1-execute/recall-baseline/summary.json`
- Final recall summary: `data/sweep_runs/20260501-124737-prod-stage1-execute/recall-after-SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY/summary.json`
- Final recall report: `data/results/20260501-124737-prod-stage1-recall-after-SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY.md`
- Final status counts: `{'ok': 12, 'observe': 7, 'improved': 3}`

Preserve probes all stayed stable:

- `PREF-AUTOMEM-SESSION-START`: 8 -> 8, top_changed=false, lost_top5=0
- `PREF-PR-TITLES`: 10 -> 10, top_changed=false, lost_top5=0
- `DEPLOY-AUTOMEM-EVALS`: 3 -> 3, top_changed=false, lost_top5=0
- `BACKUP-AUTH-DECISION`: 5 -> 5, top_changed=false, lost_top5=0
- `AUTOMEM-EVALS-BEAM-RESULT`: 2 -> 2, top_changed=false, lost_top5=0
- `AUTOMEM-EVALS-CLEANUP-RESULT`: 9 -> 9, top_changed=false, lost_top5=0
- `AUTOJACK-BLOG-PUBLISHED`: 10 -> 10, top_changed=false, lost_top5=0
- `BUGFIX-D1-SYNC`: 8 -> 8, top_changed=false, lost_top5=0
- `LOCOMO-REAL-BENCHMARK`: 10 -> 10, top_changed=false, lost_top5=0

Noise probes improved for direct targets where the target class was fully removed. Some broad noise probes still return residual non-target memories, which is expected because the query/tag classes remain populated by non-Stage-1 records.

## Post-Delete Residual Matcher Check

Raw residual check: `data/sweep_runs/20260501-124737-prod-stage1-execute/post-delete-residuals.json`

| Filter | Residual matches | Enumerated seed-tag records |
|---|---:|---:|
| `SWEEP-LOCOMO-BENCHMARK` | 0 | 0 |
| `SWEEP-BUILD-RESULTS` | 0 | 10 |
| `SWEEP-TEST-RESULTS` | 0 | 41 |
| `SWEEP-MOLTBOOK-ENGAGEMENT-PINGS` | 0 | 0 |
| `SWEEP-TWITTER-ENGAGEMENT-PINGS` | 0 | 9 |
| `SWEEP-STARTED-SESSION` | 0 | 2 |
| `SWEEP-ENGAGEMENT-WORKFLOW-SUMMARY` | 0 | 235 |

## Recommendation

Stage 1 production cleanup completed successfully. Backups exist and line counts match all deletes. Preserve counts and preserve recall probes remained stable. The Stage 1 scenario now has zero residual matches in production.

Do not proceed to broader cleanup classes from the earlier inventory without a new dry-run/refinement pass, especially session milestone overlap and workflow-summary drift outside this tightened scheduled-engagement subset.
