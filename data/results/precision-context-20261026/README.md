# Controlled context precision diagnostic

One experiment, preregistered before paid execution. Use the frozen `preregistration.json` for every selected question, item hash, server/harness revision, model, arm order and budget bound. The preregistration hash is recorded in the provider preflight, launch receipt and every case result.

Retrieve once with the canonical LongMemEval `baseline` configuration on the merged server: per-session corpus, Voyage-4/1024d, limit ten, exact question scope, no expansion/decomposition/enrichment/JIT/consolidation. Compare the unchanged full retrieved context with the order-preserving subset of those records whose session IDs are labeled support. Never insert absent support. Both arms use the same native answer and judge templates and request policies. Alternate arm order by frozen cohort position.

The cohort is all 30 preference questions plus the five historical support misses; one overlaps, so there are 34 unique questions. Report the 30-question preference stratum and the five miss controls separately. Historical grades are unchanged; freshly generated full-context answers are the paired control. Full retrieved texts, serialized model requests, raw responses, per-case answers and judge rationales are retained.

Support labels are not exhaustive relevance judgments. This is an oracle diagnostic of removing off-label context, not a deployable retrieval filter or a measured relevance precision score. A single stochastic answer/judge pass does not establish repeatability or generalize to the whole benchmark. It also changes context length; it cannot isolate relevance from token-budget effects.

The batch has a $3 subledger within the original $20 ceiling. It carries forward $9.809397650 of prior accounted spend, including all prior ambiguous liabilities. Preflight, embeddings, answers, judges, native retries and failed reservations share this subledger. The authenticated loopback proxy fails closed on unknown pricing/models, unavailable accounting or budget exhaustion. No provider credentials enter the server or answerer processes.

Execution is exploratory and local. One-off launch helpers, their tests, the unchanged official hardener, exact commands/configuration and raw per-question evidence are retained in the ignored `data/sweep_runs/precision-context-20261026/` directory. The original sealed baseline is not modified. Official benchmark harnesses and headline claims remain in `automem`.
