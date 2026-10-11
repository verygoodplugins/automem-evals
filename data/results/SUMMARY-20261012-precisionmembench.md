# PrecisionMemBench isolated-local smoke — 2026-10-12

Exploratory **AutoMem + official external wrapper**, issue #64; `maturation: cold`, `matured: blocked`. All official 89 assertions ran, no answerer/judge, no synthetic substitute, no paper baseline used as an AutoMem result. See [protocol/pins](../../docs/eval/precisionmembench.md).

| Measure | Single-turn (77 cases) | Session (12 turns, 2 scenarios) |
| --- | --- | --- |
| Passes | 11/77 | 0/12 |
| Mean precision / recall | 0.0735 / 1.0 | 0.0765 / 1.0 |
| Context-build latency mean / p50 / p95, ms | 31.88 / 31.37 / 58.84 | 47.17 / 43.28 / 70.63 |
| Pass types: active / structural / empty | 0 / 8 / 3 | 0 / 0 / 0 |

Session mean drift (`1 - precision`): 0.9235. Explicit noise isolation: 0/3 protected turns; 14 forbidden-ID occurrences. Each of 12 turns failed at least one assertion; AVA reports two failed session tests. Single-turn AVA exits 1 with 66 failed cases. These are benchmark findings, not adapter-test failures.

Single-turn category passes: alias 0/23; scope 1/12; fuzzy 0/7; type/questions 0/6; boundaries 2/6; budget 3/5; persona 2/4; relations 0/4; supersession 0/3; ranking 1/3; counter-signal 0/2; cross-user 1/1; cold-start 1/1. Supersession category failures are extra unrelated beliefs, not resurfaced superseded IDs. Raw audit: 88 recall requests, 0 exact-tag boundary violations, 0 superseded-ID occurrences, 140 resolved-record occurrences. Resolved records were ingested with `t_invalid`, but vector recall omitted that field; this temporal projection gap needs product-side investigation. Do not equate scope category failures with unauthorized leakage.

Provenance: AutoMem clean commit `3caa9d5d396ba4cb303df1fb39da7602126f60c9`; runtime image `sha256:668fccdfd77afba9be262df8b1ef944da072b72834da098bdd5fc87c7feb722d`; dedicated Compose project `pmb_92ebad9f`, loopback API 8091, bridge 8099, fresh graph/vector volumes. FastEmbed `BAAI/bge-small-en-v1.5`, 384d, no paid providers. Indexing worker enabled; every write awaited graph/vector count agreement. Enrichment/JIT/consolidation off. Limit from official budget (default 20), exact conjunctive tags, current-only recall. Model cache is not immutable-pinned; this is a smoke, not a curated reproducibility claim.

Raw official reports, indexed request/response audit, AVA logs, and verification report remain under `.agent-drafts/`. Earlier unindexed diagnostics are excluded. Zero benchmark protocol errors; one unrelated localhost quota RPC was rejected without mutation. Future default bridge port is 18099 to avoid that client. Official fixtures/scorer SHA256:

```text
beliefs.seed.json             35659b3b9a581b644fc6746e1b4e902c3e7b56c0973b546bf7b0816a69e3de98
retrieval.cases.json          09e99f0852280538abe34b03570f65583fdb10df3c554b7150f0f665d5db709c
session-retrieval.cases.json  f24a359cdb2bf50237e1ab463af938cd54a81917f64c8d97304de318aed4cc1c
buildRetrievalReport.ts       809c77fccbf0e3b3001a2c396f4c6dc515d4f1f19b293373c8abca9239fcfa9b
```

Verification: index tests 14/14; scripts discovery 34/34 (including four protocol tests); issue #64 browser DOM checks 4/4, screenshot inspected, zero page errors. Generated index includes `EXP-PRECISIONMEMBENCH`; generated dashboards remain in `.agent-drafts/` to avoid unrelated machine/worktree churn. No companion repository changes. Next: frozen narrative-clock matured comparison, temporal projection investigation, and repeated runs with immutable model pinning before publication.
