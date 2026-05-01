# Recall endpoint comparison - 2026-05-01T12:53:08

Scenario: `Realistic recall probes for AutoMem cleanup evaluation. These queries are based on observed mirror history, workflow logs, hook output classes, and prior cleanup findings. Use with runners/compare_recall_endpoints.py to compare a baseline endpoint against a cleaned endpoint.`
Baseline endpoint: `https://automem.up.railway.app`
Candidate endpoint: `https://automem.up.railway.app`
Raw responses: `data/sweep_runs/20260501-124737-prod-stage1-execute/recall-after-SWEEP-LOCOMO-BENCHMARK/raw`

## Health

| Endpoint | status | memory_count | vector_count | sync_status |
|---|---|---:|---:|---|
| baseline | healthy | 11046 | 11046 | synced |
| candidate | healthy | 10093 | 10093 | synced |

## Summary

| Query | Group | Status | baseline count | candidate count | delta | top changed | lost top-5 |
|---|---|---|---:|---:|---:|---|---:|
| PREF-AUTOMEM-SESSION-START | preserve | ok | 8 | 8 | 0 | false | 0 |
| PREF-PR-TITLES | preserve | ok | 10 | 10 | 0 | false | 0 |
| DEPLOY-AUTOMEM-EVALS | preserve | ok | 3 | 3 | 0 | false | 0 |
| BACKUP-AUTH-DECISION | preserve | ok | 5 | 5 | 0 | false | 0 |
| AUTOMEM-EVALS-BEAM-RESULT | preserve | ok | 2 | 2 | 0 | false | 0 |
| AUTOMEM-EVALS-CLEANUP-RESULT | preserve | ok | 9 | 9 | 0 | false | 0 |
| AUTOJACK-BLOG-PUBLISHED | preserve | ok | 10 | 10 | 0 | false | 0 |
| BUGFIX-D1-SYNC | preserve | ok | 8 | 8 | 0 | false | 0 |
| LOCOMO-REAL-BENCHMARK | preserve | ok | 10 | 10 | 0 | false | 0 |
| AGENT-WP-FUSION-SNIPPET | mixed | ok | 10 | 10 | 0 | false | 0 |
| AGENT-RECALL-ISSUE | mixed | ok | 10 | 10 | 0 | false | 0 |
| WORKFLOW-DAILY-CONTEXT | mixed | ok | 10 | 10 | 0 | false | 0 |
| BUILD-NOISE | noise | observe | 1 | 1 | 0 | false | 0 |
| TEST-NOISE | noise | observe | 2 | 2 | 0 | false | 0 |
| SESSION-MILESTONE-NOISE | noise | observe | 5 | 5 | 0 | false | 0 |
| WORKFLOW-SUMMARY-NOISE | noise | observe | 10 | 10 | 0 | false | 0 |
| TWITTER-ENGAGEMENT-PING | noise | observe | 1 | 1 | 0 | false | 0 |
| MOLTBOOK-ENGAGEMENT-PING | noise | observe | 1 | 1 | 0 | false | 0 |
| AGENT-RESULT-NOISE | noise | observe | 10 | 10 | 0 | false | 0 |
| WORK-PATTERN-NOISE | noise | observe | 3 | 3 | 0 | false | 0 |
| STARTED-SESSION-NOISE | noise | observe | 10 | 10 | 0 | false | 0 |
| LOCOMO-FIXTURE-NOISE | noise | improved | 10 | 0 | -10 | true | 5 |

## Details

### PREF-AUTOMEM-SESSION-START (preserve, ok)
User preference/process memory that should survive any cleanup.

Query: `What memory usage preferences should I follow at session start for AutoMem?`
Params: `{"tags":["preference"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `9c45605e-cc86-448a-9854-cf2fb79b59f1` [0.878174640020872] Meta-correction: several transient AutoMem notes from this turn were unnecessary. Existing project preference already says avoid attentiveness/performance memory; follow that and s
2. `83e51419-e437-46ec-b2c1-761186967220` [0.85023957748089] No additional durable memory from this turn beyond existing AutoMem usage preference. Prefer not to store further meta-process notes.
3. `14bbbd46-771e-44fe-abba-fe00df8f6490` [0.8459229270858154] User working in autohub expects early AutoMem usage from AGENTS.md: recall preferences and project-specific context before substantive repo research. This affects planning and debu

Candidate top:
1. `9c45605e-cc86-448a-9854-cf2fb79b59f1` [0.8781491388911459] Meta-correction: several transient AutoMem notes from this turn were unnecessary. Existing project preference already says avoid attentiveness/performance memory; follow that and s
2. `83e51419-e437-46ec-b2c1-761186967220` [0.8502945973511831] No additional durable memory from this turn beyond existing AutoMem usage preference. Prefer not to store further meta-process notes.
3. `14bbbd46-771e-44fe-abba-fe00df8f6490` [0.8459389744564557] User working in autohub expects early AutoMem usage from AGENTS.md: recall preferences and project-specific context before substantive repo research. This affects planning and debu

### PREF-PR-TITLES (preserve, ok)
GitHub workflow preference; protects recent durable user correction.

Query: `How should GitHub PR titles be formatted, and should they use a Codex prefix?`
Params: `{"tags":["preference"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `1ba73c00-0290-4b7e-bbab-19a100554269` [0.7194327470198174] PR title preference correction. For GitHub PRs use the repo’s conventional-commit style titles such as `feat: ...`; do not add `[codex]` prefixes from generic publish workflow conv
2. `649c3a65-3bb9-4919-a726-a478bdb298de` [0.48261454590264274] AutoMem tag convention: BARE tags only, no prefixes. Use tags=["mcp-automem"] not ["project/mcp-automem"]. The project/ prefix scheme was tested locally for ~24h in March 2026 and 
3. `100e3def-ab3d-43b9-99d2-58eac54ab662` [0.45869134698620756] Railway deploy links must include Jack’s referral code. Use `?referralCode=VuFE6g&utm_medium=integration&utm_source=github&utm_campaign=generic` on all `https://railway.com/deploy/

Candidate top:
1. `1ba73c00-0290-4b7e-bbab-19a100554269` [0.7194307395560057] PR title preference correction. For GitHub PRs use the repo’s conventional-commit style titles such as `feat: ...`; do not add `[codex]` prefixes from generic publish workflow conv
2. `649c3a65-3bb9-4919-a726-a478bdb298de` [0.48261253843873453] AutoMem tag convention: BARE tags only, no prefixes. Use tags=["mcp-automem"] not ["project/mcp-automem"]. The project/ prefix scheme was tested locally for ~24h in March 2026 and 
3. `100e3def-ab3d-43b9-99d2-58eac54ab662` [0.45868933952224794] Railway deploy links must include Jack’s referral code. Use `?referralCode=VuFE6g&utm_medium=integration&utm_source=github&utm_campaign=generic` on all `https://railway.com/deploy/

### DEPLOY-AUTOMEM-EVALS (preserve, ok)
Deployment memories should be unchanged by build/test cleanup.

Query: `What production deployments happened for automem-evals on docker or vercel?`
Params: `{"tags":["deployment"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `750bbc60-c9a9-470b-b188-02282afc4ab3` [0.7282814939155717] Deployed automem-evals to production on vercel
2. `0446e46e-1790-404d-8627-77b509ec1ef4` [0.7278840182822127] Deployed automem-evals to production on docker
3. `150459e6-f929-42a7-b593-19f1d5786a24` [0.5960975239133433] Deployed automem-evals to testing on vercel

Candidate top:
1. `750bbc60-c9a9-470b-b188-02282afc4ab3` [0.7282794905841352] Deployed automem-evals to production on vercel
2. `0446e46e-1790-404d-8627-77b509ec1ef4` [0.7278820149507762] Deployed automem-evals to production on docker
3. `150459e6-f929-42a7-b593-19f1d5786a24` [0.5960955205819325] Deployed automem-evals to testing on vercel

### BACKUP-AUTH-DECISION (preserve, ok)
AutoMem backup auth/testing decisions should survive cleanup.

Query: `What was decided about AutoMem backup auth, API testing, and admin token requirements?`
Params: `{"tags":["automem","backup"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `7c21acf1-ba53-4274-ac0a-1656b80d39ff` [2.27914406550754] GitHub Actions backup failing with 'Connection reset by peer' (error 104). Root cause: FALKORDB_HOST secret was using Railway internal hostname (falkordb.railway.internal) which is
2. `adbccf01-56ce-4b7c-874b-ff4e45c872db` [0.7667339134907746] AutoMem /backup auth decision. GET /backup should require ADMIN_API_TOKEN via the existing admin auth path, not the normal API token, because it exports the full corpus in one call
3. `79df8778-0876-44c6-8cbf-39dc25139517` [0.7650311798069139] AutoMem /backup v1 auth scope update. Current task supersedes the prior admin-only note: GET /backup should use existing API-token auth via X-Api-Key/Bearer, with admin-key separat

Candidate top:
1. `7c21acf1-ba53-4274-ac0a-1656b80d39ff` [2.279142066791896] GitHub Actions backup failing with 'Connection reset by peer' (error 104). Root cause: FALKORDB_HOST secret was using Railway internal hostname (falkordb.railway.internal) which is
2. `adbccf01-56ce-4b7c-874b-ff4e45c872db` [0.7667319147750338] AutoMem /backup auth decision. GET /backup should require ADMIN_API_TOKEN via the existing admin auth path, not the normal API token, because it exports the full corpus in one call
3. `79df8778-0876-44c6-8cbf-39dc25139517` [0.7650291810912053] AutoMem /backup v1 auth scope update. Current task supersedes the prior admin-only note: GET /backup should use existing API-token auth via X-Api-Key/Bearer, with admin-key separat

### AUTOMEM-EVALS-BEAM-RESULT (preserve, ok)
Benchmark/eval results should survive benchmark-fixture cleanup.

Query: `What happened in the automem-evals BEAM V1 vs V2 full bucket result?`
Params: `{"tags":["automem-evals","beam"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `0cea03b4-d337-4546-99b3-9b264923e07d` [0.7006496041284603] BEAM V1 vs V2 full bucket result (100K, n=400, gpt-5-mini both): V2 is -2.5pp net vs V1 (76.25% → 73.75%). Wins: abstention +15pp, knowledge_update +7.5pp (forensics-predicted), su
2. `409a665c-635f-47b5-8bf4-ee754e774d87` [0.5035134268407545] V2 extraction shim (runners/beam_shim_v2.py) working in BEAM smoke. Uses mem0's FACT_RETRIEVAL_PROMPT (pinned SHA daa4495). Stats from first 73 chunks: 100% extraction success, avg

Candidate top:
1. `0cea03b4-d337-4546-99b3-9b264923e07d` [0.7008411244487214] BEAM V1 vs V2 full bucket result (100K, n=400, gpt-5-mini both): V2 is -2.5pp net vs V1 (76.25% → 73.75%). Wins: abstention +15pp, knowledge_update +7.5pp (forensics-predicted), su
2. `409a665c-635f-47b5-8bf4-ee754e774d87` [0.5034023371610798] V2 extraction shim (runners/beam_shim_v2.py) working in BEAM smoke. Uses mem0's FACT_RETRIEVAL_PROMPT (pinned SHA daa4495). Stats from first 73 chunks: 100% extraction success, avg

### AUTOMEM-EVALS-CLEANUP-RESULT (preserve, ok)
Recent cleanup findings should remain recallable.

Query: `What did we learn about SWEEP-MEMORY-CACHE, SWEEP-SESSION-MILESTONE, and local mirror cleanup?`
Params: `{"tags":["automem-evals"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `18177b14-9570-4767-a78b-5bb670e07207` [0.5436432400190137] AutoMem cleanup local clone blocker. corpus_sweep_v1 full dry-run against prod API clone stopped on SWEEP-WORKFLOW-SUMMARY: current prefix guard matched 161 vs expected 600-1500; S
2. `409a665c-635f-47b5-8bf4-ee754e774d87` [0.33990283402530863] V2 extraction shim (runners/beam_shim_v2.py) working in BEAM smoke. Uses mem0's FACT_RETRIEVAL_PROMPT (pinned SHA daa4495). Stats from first 73 chunks: 100% extraction success, avg
3. `0cea03b4-d337-4546-99b3-9b264923e07d` [0.3381643918115098] BEAM V1 vs V2 full bucket result (100K, n=400, gpt-5-mini both): V2 is -2.5pp net vs V1 (76.25% → 73.75%). Wins: abstention +15pp, knowledge_update +7.5pp (forensics-predicted), su

Candidate top:
1. `18177b14-9570-4767-a78b-5bb670e07207` [0.5436412507702675] AutoMem cleanup local clone blocker. corpus_sweep_v1 full dry-run against prod API clone stopped on SWEEP-WORKFLOW-SUMMARY: current prefix guard matched 161 vs expected 600-1500; S
2. `409a665c-635f-47b5-8bf4-ee754e774d87` [0.3399008447765882] V2 extraction shim (runners/beam_shim_v2.py) working in BEAM smoke. Uses mem0's FACT_RETRIEVAL_PROMPT (pinned SHA daa4495). Stats from first 73 chunks: 100% extraction success, avg
3. `0cea03b4-d337-4546-99b3-9b264923e07d` [0.33816240256304014] BEAM V1 vs V2 full bucket result (100K, n=400, gpt-5-mini both): V2 is -2.5pp net vs V1 (76.25% → 73.75%). Wins: abstention +15pp, knowledge_update +7.5pp (forensics-predicted), su

### AUTOJACK-BLOG-PUBLISHED (preserve, ok)
Published artifacts are an explicit preserve class.

Query: `Which AutoJack blog posts were recently published and what topics did they cover?`
Params: `{"tags":["autojack-blog","published"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `3723ad86-4fc0-4a05-912a-43a730020178` [0.40207133493793723] PUBLISHED: "604 Seconds to Nothing" to drunk.support (Post #560). Topics: fire-and-forget agent anti-pattern, awaiting_review loop, PR #217. Format: Problem Breakdown. AutoJack voi
2. `09e19f2b-1d06-424c-91af-6516404b41f8` [0.39717696327352103] Backfilled published post “Skills Don't Need a Server (Yet)” on drunk.support (#597). Workflow created content but skipped memory.store_memory, so this entry prevents Phase 1.2 ded
3. `ea0e7834-6f1b-433e-90ed-ff1de9db82dc` [0.38895926407354675] PUBLISHED: "We Have a Music Video Pipeline Now" to drunk.support. Topics: Wan2.2 MLX local text-to-video on Apple Silicon, FFmpeg audio mux, Slack external upload API workspace-awa

Candidate top:
1. `3723ad86-4fc0-4a05-912a-43a730020178` [0.4020693516011831] PUBLISHED: "604 Seconds to Nothing" to drunk.support (Post #560). Topics: fire-and-forget agent anti-pattern, awaiting_review loop, PR #217. Format: Problem Breakdown. AutoJack voi
2. `09e19f2b-1d06-424c-91af-6516404b41f8` [0.39717497993674766] Backfilled published post “Skills Don't Need a Server (Yet)” on drunk.support (#597). Workflow created content but skipped memory.store_memory, so this entry prevents Phase 1.2 ded
3. `ea0e7834-6f1b-433e-90ed-ff1de9db82dc` [0.38895728073676694] PUBLISHED: "We Have a Music Video Pipeline Now" to drunk.support. Topics: Wan2.2 MLX local text-to-video on Apple Silicon, FFmpeg audio mux, Slack external upload API workspace-awa

### BUGFIX-D1-SYNC (preserve, ok)
Bugfix/solution memories should survive session/build/test cleanup.

Query: `What was the root cause of the D1 sync foreign-key storm and how was it fixed?`
Params: `{"tags":["bugfix","solution"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `e65659b8-5734-4f1a-8e2b-a09dc4156bef` [0.5727025727576003] Cleared April 22 2026 D1 sync FK storm in autohub without new local corruption. Root causes were remote D1 drift for conversations after local timestamp-repair updates, plus 7 stal
2. `987081d2-0651-4d94-b027-fa5835851dc4` [0.4601498814466628] Recovered autohub SQLite telemetry on 2026-04-22 after local data/hub-unified.db corruption. Promoted a .recover-generated DB, cleaned lost_and_found plus orphaned FK rows, and add
3. `d8b8b728-25ff-4a9f-83aa-eea2312d0f89` [0.2582606788708912] Claude session in wp-fusion-ecommerce. on branch fix/surecart-renewal-overwrites-deal. - Made 3 commits. - Significant commit pattern: fix[:\(]. - Focused on: feature_development, 

Candidate top:
1. `e65659b8-5734-4f1a-8e2b-a09dc4156bef` [0.5727005953107961] Cleared April 22 2026 D1 sync FK storm in autohub without new local corruption. Root causes were remote D1 drift for conversations after local timestamp-repair updates, plus 7 stal
2. `987081d2-0651-4d94-b027-fa5835851dc4` [0.4601479039996978] Recovered autohub SQLite telemetry on 2026-04-22 after local data/hub-unified.db corruption. Promoted a .recover-generated DB, cleaned lost_and_found plus orphaned FK rows, and add
3. `d8b8b728-25ff-4a9f-83aa-eea2312d0f89` [0.2582587014237976] Claude session in wp-fusion-ecommerce. on branch fix/surecart-renewal-overwrites-deal. - Made 3 commits. - Significant commit pattern: fix[:\(]. - Focused on: feature_development, 

### LOCOMO-REAL-BENCHMARK (preserve, ok)
Protect real LoCoMo implementation/result memories while deleting locomo-test fixtures.

Query: `What is the real AutoMem LoCoMo benchmark implementation status or benchmark result, not Caroline/Melanie test conversations?`
Params: `{"tags":["automem","locomo"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `5855375b-1611-451f-9082-c83d48479872` [6.4861538461538455] [MILESTONE] First LoCoMo benchmark run initiated for AutoMem (Oct 15, 2025). Fixed 201 status code bug in test harness, configured Docker with OpenAI embeddings, and launched full 
2. `1f70175b-256a-449b-a45d-e4ee6586e250` [6.164423076923076] [BENCHMARK-IMPLEMENTATION] Built complete LoCoMo benchmark integration for AutoMem (Oct 15, 2025). Created test harness at tests/benchmarks/test_locomo.py that loads 10 conversatio
3. `4d0b35a6-7421-44dd-9b15-06216721aa5c` [0.5968506845868303] Benchmark entrypoints were not loading ~/.config/automem/.env, so OPENAI_API_KEY never reached standalone LoCoMo/LongMemEval runs and cat-5 judging silently skipped. Fixed by addin

Candidate top:
1. `5855375b-1611-451f-9082-c83d48479872` [6.4861538461538455] [MILESTONE] First LoCoMo benchmark run initiated for AutoMem (Oct 15, 2025). Fixed 201 status code bug in test harness, configured Docker with OpenAI embeddings, and launched full 
2. `1f70175b-256a-449b-a45d-e4ee6586e250` [6.164423076923076] [BENCHMARK-IMPLEMENTATION] Built complete LoCoMo benchmark integration for AutoMem (Oct 15, 2025). Created test harness at tests/benchmarks/test_locomo.py that loads 10 conversatio
3. `4d0b35a6-7421-44dd-9b15-06216721aa5c` [0.5968487123518831] Benchmark entrypoints were not loading ~/.config/automem/.env, so OPENAI_API_KEY never reached standalone LoCoMo/LongMemEval runs and cat-5 judging silently skipped. Fixed by addin

### AGENT-WP-FUSION-SNIPPET (mixed, ok)
Agent summaries may be noisy, but customer/support task recall can be valuable.

Query: `What did the WP Fusion agent do for the WooCommerce total orders snippet task?`
Params: `{"tags":["agent","result-summary"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `14c164dd-bffd-44b2-afae-ccdb1feab40b` [0.6351735304225243] Agent wp-fusion-expert completed task agent-mntsr33b-d2vbo in 330s (rounds: 0, tools: 11). Task: The user wants WooCommerce to only price things in Hong Kong Dollars (HKD) — "Canto
2. `e8eee7c2-13f1-49e9-9448-9d4966ded82e` [0.5806813255809542] Agent wordpress-specialist completed task agent-mng9wygj-5syo3 in 235s (rounds: 0, tools: 33). Task: Check the following AffiliateWP affiliates on wpfusion.com and report back on e
3. `024cea78-4f30-4597-a7fe-3fdd07078cac` [0.5384703849639082] Agent wordpress-specialist completed task agent-mng9u426-gw49x in 585s (rounds: 0, tools: 34). Task: INVESTIGATION ONLY — no code changes, no worktrees, no branches, no PRs. Custom

Candidate top:
1. `14c164dd-bffd-44b2-afae-ccdb1feab40b` [0.6351715632378343] Agent wp-fusion-expert completed task agent-mntsr33b-d2vbo in 330s (rounds: 0, tools: 11). Task: The user wants WooCommerce to only price things in Hong Kong Dollars (HKD) — "Canto
2. `e8eee7c2-13f1-49e9-9448-9d4966ded82e` [0.5806793583962706] Agent wordpress-specialist completed task agent-mng9wygj-5syo3 in 235s (rounds: 0, tools: 33). Task: Check the following AffiliateWP affiliates on wpfusion.com and report back on e
3. `024cea78-4f30-4597-a7fe-3fdd07078cac` [0.5384684177792567] Agent wordpress-specialist completed task agent-mng9u426-gw49x in 585s (rounds: 0, tools: 34). Task: INVESTIGATION ONLY — no code changes, no worktrees, no branches, no PRs. Custom

### AGENT-RECALL-ISSUE (mixed, ok)
Checks whether agent-result cleanup would lose useful GitHub issue context.

Query: `Which GitHub issue was created about memory recall being broken in chat, voice, or social contexts?`
Params: `{"tags":["agent","result-summary"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `6b70f476-5ab4-4f80-9678-858a55657d26` [0.4063649942719017] Agent hub-developer completed task agent-mnvaub4w-ks9rr in 332s (rounds: 0, tools: 41). Task: The Slack adapter for workspace TP56GEBQR (mastermind workspace) is not allowing the b
2. `91297c80-1c9b-4e5d-8aa9-ab78b1f63f68` [0.3992596004537344] Agent hub-developer completed task agent-mng6xhzq-nfltw in 1204s (rounds: 0, tools: 69). Task: Analyze today's session failures and fix them. Here's what you need to do:  1. First,
3. `88a3a171-100d-4ded-aca4-218ef827fb34` [0.3916382025266001] Agent hub-developer completed task agent-mo1uu0rt-3zgwp in 8s (rounds: 0, tools: 0). Task: Investigate a visual glitch in the AutoHub voice UI. When agent text is streaming (before

Candidate top:
1. `6b70f476-5ab4-4f80-9678-858a55657d26` [0.40636303220553727] Agent hub-developer completed task agent-mnvaub4w-ks9rr in 332s (rounds: 0, tools: 41). Task: The Slack adapter for workspace TP56GEBQR (mastermind workspace) is not allowing the b
2. `91297c80-1c9b-4e5d-8aa9-ab78b1f63f68` [0.3992576383869391] Agent hub-developer completed task agent-mng6xhzq-nfltw in 1204s (rounds: 0, tools: 69). Task: Analyze today's session failures and fix them. Here's what you need to do:  1. First,
3. `88a3a171-100d-4ded-aca4-218ef827fb34` [0.3916362404596505] Agent hub-developer completed task agent-mo1uu0rt-3zgwp in 8s (rounds: 0, tools: 0). Task: Investigate a visual glitch in the AutoHub voice UI. When agent text is streaming (before

### WORKFLOW-DAILY-CONTEXT (mixed, ok)
Some workflow summaries may be useful context; treat top-result changes as review-worthy.

Query: `What daily context or morning routine summaries matter for current work?`
Params: `{"tags":["workflow","summary"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `a3887711-97c8-43e8-b08a-6945906fa667` [0.623454429744033] Good morning, AutoJack! 🌙➡️☀️  It's **Tuesday, April 21st, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running toda
2. `a6cb189e-da8a-4001-b1b8-2c444afaa87f` [0.6054818091435957] Good morning, AutoJack! 🌙➡️☀️  It's **Monday, March 23rd, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running today
3. `cd55f5a0-0867-4f4d-b85d-ee543abc25ac` [0.5995700195689879] Good morning, AutoJack! 🌙➡️☀️  It's **Wednesday, April 22nd, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running to

Candidate top:
1. `a3887711-97c8-43e8-b08a-6945906fa667` [0.623452472501929] Good morning, AutoJack! 🌙➡️☀️  It's **Tuesday, April 21st, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running toda
2. `a6cb189e-da8a-4001-b1b8-2c444afaa87f` [0.6054798519010417] Good morning, AutoJack! 🌙➡️☀️  It's **Monday, March 23rd, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running today
3. `cd55f5a0-0867-4f4d-b85d-ee543abc25ac` [0.5995680623267297] Good morning, AutoJack! 🌙➡️☀️  It's **Wednesday, April 22nd, 2026**, and I've got your daily context briefing ready. Here's everything you need to know to hit the ground running to

### BUILD-NOISE (noise, observe)
Mechanical build hook records should disappear after build cleanup.

Query: `Build succeeded in automem-website using npm`
Params: `{"tags":["build"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `8b8b7380-8a60-4ba7-a2ce-a91326af6489` [0.9533440176113426] Build succeeded in automem-website using npm

Candidate top:
1. `8b8b7380-8a60-4ba7-a2ce-a91326af6489` [0.9533420649994856] Build succeeded in automem-website using npm

### TEST-NOISE (noise, observe)
Mechanical test hook records should disappear after test cleanup.

Query: `Test suite passed 0 tests in autohub using jest vitest`
Params: `{"tags":["test"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `a6a78a3a-ea30-4682-810f-82992738ca7e` [0.943262558990299] Test suite passed: 0 tests in autohub using jest/vitest. Command: npm test 2>&1
2. `f9f38683-86c4-4de5-8281-5fedf982238a` [0.940621810900722] Test suite passed: 0 tests in autohub using jest/vitest. Command: npm test 2>&1 | tail -20

Candidate top:
1. `a6a78a3a-ea30-4682-810f-82992738ca7e` [0.9432606109979572] Test suite passed: 0 tests in autohub using jest/vitest. Command: npm test 2>&1
2. `f9f38683-86c4-4de5-8281-5fedf982238a` [0.9406198629079173] Test suite passed: 0 tests in autohub using jest/vitest. Command: npm test 2>&1 | tail -20

### SESSION-MILESTONE-NOISE (noise, observe)
Session milestone summaries are a cleanup target, but only after preserve-tag exclusions.

Query: `Claude session in autohub modified files change size branch`
Params: `{"tags":["session_milestone","session-milestone"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `d3760af9-b86e-4e1d-b6d5-c9181505dd3f` [0.9117740468318352] Claude session in autohub. on branch main. - Modified 17 files. - Modified code file: src/claude/tools/execute.js. - Change size: small
2. `4b65702c-f46a-4a22-8ece-6d1275b710e4` [0.8698723393250964] Claude session in autohub. on branch main. - Modified 45 files. - Modified code file: scripts/realtime-mcp-agent.js. - Change size: medium
3. `b95a571d-8cf8-4890-8224-1b9cc38afcf6` [0.8649876979349987] Claude session in autohub. on branch main. - Modified 14 files. - Modified code file: scripts/tee-rotate.js. - Change size: medium

Candidate top:
1. `d3760af9-b86e-4e1d-b6d5-c9181505dd3f` [0.911772108154501] Claude session in autohub. on branch main. - Modified 17 files. - Modified code file: src/claude/tools/execute.js. - Change size: small
2. `4b65702c-f46a-4a22-8ece-6d1275b710e4` [0.8698704006471001] Claude session in autohub. on branch main. - Modified 45 files. - Modified code file: scripts/realtime-mcp-agent.js. - Change size: medium
3. `b95a571d-8cf8-4890-8224-1b9cc38afcf6` [0.8649857592578897] Claude session in autohub. on branch main. - Modified 14 files. - Modified code file: scripts/tee-rotate.js. - Change size: medium

### WORKFLOW-SUMMARY-NOISE (noise, observe)
Scheduled workflow execution summaries are a cleanup target.

Query: `Workflow Execution Summary Moltbook Engagement scheduled workflow summary`
Params: `{"tags":["workflow","summary","scheduled"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `59f54755-1cab-4eda-92e9-801b01e59cab` [0.8665629996889275] # Moltbook Engagement Workflow Summary  **Workflow:** `moltbook-engagement.md`   **Status:** ⚠️ **Partial Failure** (13/14 steps completed)   **Execution Date:** March 22, 2026  --
2. `05011222-59bc-472c-bd7e-37cc15d3f248` [0.8641604539817838] # Moltbook Engagement Summary  **Workflow:** `moltbook-engagement.md`   **Execution:** 14 steps | 0 failures   **Timestamp:** 2026-03-25  ---  ## 📬 Direct Messages & Notifications 
3. `e2cf2ce9-67a1-4a8e-847b-c6791e5e7805` [0.8640414108038773] # Workflow Summary: Moltbook Engagement  **Status:** ⚠️ PARTIAL FAILURE (1 of 14 steps failed)   **File:** autohub/workflows/heartbeat/moltbook-engagement.md   **Execution Time:** 

Candidate top:
1. `59f54755-1cab-4eda-92e9-801b01e59cab` [0.8665610671993569] # Moltbook Engagement Workflow Summary  **Workflow:** `moltbook-engagement.md`   **Status:** ⚠️ **Partial Failure** (13/14 steps completed)   **Execution Date:** March 22, 2026  --
2. `05011222-59bc-472c-bd7e-37cc15d3f248` [0.8641585214921812] # Moltbook Engagement Summary  **Workflow:** `moltbook-engagement.md`   **Execution:** 14 steps | 0 failures   **Timestamp:** 2026-03-25  ---  ## 📬 Direct Messages & Notifications 
3. `e2cf2ce9-67a1-4a8e-847b-c6791e5e7805` [0.8640394783143004] # Workflow Summary: Moltbook Engagement  **Status:** ⚠️ PARTIAL FAILURE (1 of 14 steps failed)   **File:** autohub/workflows/heartbeat/moltbook-engagement.md   **Execution Time:** 

### TWITTER-ENGAGEMENT-PING (noise, observe)
Repeated Twitter engagement status pings are a cleanup target.

Query: `twitter engagement action skip no fresh signal posted false`
Params: `{"tags":["twitter-posts"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `bb531a91-3de2-4db4-8575-7101ea70a4f1` [0.7718971343566551] twitter engagement: action=skip, reason=no_fresh_signal, candidates=0, posted=false.

Candidate top:
1. `bb531a91-3de2-4db4-8575-7101ea70a4f1` [0.7718952060750257] twitter engagement: action=skip, reason=no_fresh_signal, candidates=0, posted=false.

### MOLTBOOK-ENGAGEMENT-PING (noise, observe)
Repeated Moltbook engagement status pings are a cleanup target.

Query: `moltbook engagement action post high_signal_digest candidates posted true`
Params: `{"tags":["moltbook-engagement"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `600911cc-ac33-4d0f-a923-79fa3848958b` [0.8156110879585199] moltbook engagement: action=post, reason=high_signal_digest, candidates=8, posted=true.

Candidate top:
1. `600911cc-ac33-4d0f-a923-79fa3848958b` [0.8156091642919496] moltbook engagement: action=post, reason=high_signal_digest, candidates=8, posted=true.

### AGENT-RESULT-NOISE (noise, observe)
Generic agent result summaries are a cleanup candidate after stronger probes.

Query: `Agent hub-developer completed task rounds tools result summary`
Params: `{"tags":["agent","result-summary"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `6ec8ba07-90fe-4a3d-946b-c163ccd63d4b` [0.6958576731081018] Agent hub-developer completed task agent-mng2noa7-m2iww in 806s (rounds: 0, tools: 8). Task: Review the conversation logs/database for the session on April 1, 2026 (~3:18 PM GMT+2)
2. `471cbd5d-66af-45dd-b143-9f4e5f016106` [0.6891210987074845] Agent hub-developer completed task agent-mmecop6p-67ylj in 100s (rounds: 0, tools: 18). Task: You're picking up from a previous hub-developer agent's work on PR #173: https://githu
3. `91297c80-1c9b-4e5d-8aa9-ab78b1f63f68` [0.6539985657452482] Agent hub-developer completed task agent-mng6xhzq-nfltw in 1204s (rounds: 0, tools: 69). Task: Analyze today's session failures and fix them. Here's what you need to do:  1. First,

Candidate top:
1. `6ec8ba07-90fe-4a3d-946b-c163ccd63d4b` [0.6958557548156635] Agent hub-developer completed task agent-mng2noa7-m2iww in 806s (rounds: 0, tools: 8). Task: Review the conversation logs/database for the session on April 1, 2026 (~3:18 PM GMT+2)
2. `471cbd5d-66af-45dd-b143-9f4e5f016106` [0.6891191804145833] Agent hub-developer completed task agent-mmecop6p-67ylj in 100s (rounds: 0, tools: 18). Task: You're picking up from a previous hub-developer agent's work on PR #173: https://githu
3. `91297c80-1c9b-4e5d-8aa9-ab78b1f63f68` [0.6539966474523405] Agent hub-developer completed task agent-mng6xhzq-nfltw in 1204s (rounds: 0, tools: 69). Task: Analyze today's session failures and fix them. Here's what you need to do:  1. First,

### WORK-PATTERN-NOISE (noise, observe)
Automated work-pattern summaries are a cleanup candidate.

Query: `Work pattern in autohub focuses on bug fixing work style automated`
Params: `{"tags":["work_style","automated"],"tag_mode":"all","limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `24fd6360-62c8-4258-9906-a1472e00afc6` [1.1797563132454862] Work pattern in autohub: focuses on bug_fixing
2. `543490ab-889a-4cbd-9e32-af7a65c5799c` [1.1676315877617607] Work pattern in autohub: focuses on feature_development, bug_fixing
3. `7eefb6e1-f16f-4e09-bb2d-e981d25c997c` [1.1619000579440908] Work pattern in autohub: focuses on bug_fixing, refactoring

Candidate top:
1. `24fd6360-62c8-4258-9906-a1472e00afc6` [1.179754399507684] Work pattern in autohub: focuses on bug_fixing
2. `543490ab-889a-4cbd-9e32-af7a65c5799c` [1.1676296740239713] Work pattern in autohub: focuses on feature_development, bug_fixing
3. `7eefb6e1-f16f-4e09-bb2d-e981d25c997c` [1.1618981442063014] Work pattern in autohub: focuses on bug_fixing, refactoring

### STARTED-SESSION-NOISE (noise, observe)
Cursor session-start records are a cleanup target.

Query: `Started session in project claude automation hub branch`
Params: `{"tags":["session-start"],"limit":10}`

Diff: `{"count_delta":0,"returned_delta":0,"top_changed":false,"lost_top5":[],"gained_top5":[]}`

Baseline top:
1. `4a88ff24-ff83-4ed0-b5d0-685e0220f139` [6.773571428571428] Started session in project: claude-automation-hub on branch: feature/new-chat-ui - And can you confirm that your structure matches the anthropic suggested format outlined below?  `
2. `78d9e948-f262-439e-96f5-5e948afa5224` [6.773571428571428] Started session in project: claude-automation-hub on branch: feature/new-chat-ui - Unrelated to this project, I'm running out of usage in cursor. I want to make Sonnet 4.5 in Claud
3. `924c56db-65b7-4358-8f51-684931458a05` [6.758571428571428] Started session in project: claude-automation-hub on branch: main - I don't think so because the memories are only available when you create a new conversation. They don't get stor

Candidate top:
1. `4a88ff24-ff83-4ed0-b5d0-685e0220f139` [6.773571428571428] Started session in project: claude-automation-hub on branch: feature/new-chat-ui - And can you confirm that your structure matches the anthropic suggested format outlined below?  `
2. `78d9e948-f262-439e-96f5-5e948afa5224` [6.773571428571428] Started session in project: claude-automation-hub on branch: feature/new-chat-ui - Unrelated to this project, I'm running out of usage in cursor. I want to make Sonnet 4.5 in Claud
3. `924c56db-65b7-4358-8f51-684931458a05` [6.758571428571428] Started session in project: claude-automation-hub on branch: main - I don't think so because the memories are only available when you create a new conversation. They don't get stor

### LOCOMO-FIXTURE-NOISE (noise, improved)
Synthetic LoCoMo fixture memories are a cleanup target.

Query: `Caroline Melanie cup guitar pottery locomo test conversation`
Params: `{"tags":["locomo-test"],"limit":10}`

Diff: `{"count_delta":-10,"returned_delta":-10,"top_changed":true,"lost_top5":["3c0ff9e7-2bb0-46ec-b7a2-a054cd3f5579","c03e8479-073c-43dd-a51b-abfa408110ab","943ccd49-1b42-489b-9db6-85e3b4e610a5","12fab9ac-8541-4313-8f45-e48ce31fab78","0095b734-a3cd-4e9f-aee7-2a18328add7f"],"gained_top5":[]}`

Baseline top:
1. `3c0ff9e7-2bb0-46ec-b7a2-a054cd3f5579` [0.6202199076862333] Caroline: Oh man, sorry to hear that, Melanie. I hope you're okay. Pottery's a great way to relax, so it must have been tough taking a break. Need any help?
2. `c03e8479-073c-43dd-a51b-abfa408110ab` [0.6182987681802983] Caroline: Wow, Melanie! I'm getting creative too, just learning the piano. What made you try pottery?
3. `943ccd49-1b42-489b-9db6-85e3b4e610a5` [0.6080890931826067] Melanie: Thanks, Caroline! I'm excited to see where pottery takes me. Anything coming up you're looking forward to?

Candidate top:
