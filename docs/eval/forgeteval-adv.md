# ForgetEval-Adv: exploratory local primitive baseline

This is an exploratory adapter-policy result for [issue #31](https://github.com/verygoodplugins/automem-evals/issues/31), not an official AutoMem benchmark claim. All 385 released cases ran unchanged; 234/385 passed (60.78%), with zero adapter errors or exclusions. No LLM judge or paid calls were used.

Checked [draft PR #59](https://github.com/verygoodplugins/automem-evals/pull/59) first: preserved commit `7c1db36449d2363c85aa103497ed19b9d1b1b52a` documents STALE, not ForgetEval. Its distinction between explicit mutation and inferred propagation informs this scope; no duplicate scout files were copied.

Protocol and cases: [Lethe at b6053b7](https://github.com/deeplethe/lethe/tree/b6053b7bdacc78a91b9ea4bb25f32edad278c495/bench/forgeteval), MIT (notice preserved beside artifacts). [ForgetEval paper](https://arxiv.org/abs/2606.15903), [StateMemBench/#50](https://github.com/verygoodplugins/automem-evals/issues/50), and [MemLeak](https://arxiv.org/abs/2606.29788) motivate complementary explicit mutation, evolving-state, and residual-leak probes. No scores for those other benchmarks were computed.

## Counts and artifacts

Artifacts: [`data/results/forgeteval-adv/20261008/`](../../data/results/forgeteval-adv/20261008/). Each category JSON includes every upstream case, returned text, mutation targets/IDs/stages, and missing/leaked substrings. `summary.json`, `provenance.json`, and `graph-residual.json` preserve totals, pins/configuration, and actual HTTP diagnostic payloads.

| Category | Pass / total | Errors |
| --- | ---: | ---: |
| substring_trap | 26/36 | 0 |
| prefix_collision | 23/39 | 0 |
| paraphrase_supersession | 30/38 | 0 |
| negation_trap | 38/40 | 0 |
| temporal_qualifier | 37/37 | 0 |
| shared_attribute | 39/40 | 0 |
| compound_fact | 0/40 | 0 |
| identifier_obfuscation | 4/38 | 0 |
| cross_lingual_identifier | 1/38 | 0 |
| recursive_supersession | 36/39 | 0 |
| Graph-residual extension, top-k text | 10/10 | 0 |
| Graph-residual extension, full returned rows | 5/10 | 0 |

## What failed

- **Compound fact 0/40:** the first two official cases reproduce the earlier 0/2 observation. `_01` invalidates the Berlin-and-Stripe row when changing residence; Stripe disappears. `_02` invalidates the Jamie-and-Google row when changing employer; marriage disappears. All 40 lose required unaffected clauses. Whole-row supersession is consistent, but needs fact decomposition or a justified partial-edit planner to preserve independent facts.
- **Prefix collision 23/39:** the earlier issue's 1/2 is a historical unpinned subset, not this full-suite denominator. This run's official `_01` and `_02` both pass. `_12` semantically selects TKT-1000 for "ticket TKT-100 record", deletes the sibling, and retains TKT-100: both width and target-selection failure. `_19`–`_28` and several later cases take the literal substring path and delete prefix-sharing siblings (for example `sk_live_12345_test` along with `sk_live_12345`). The trace separates wrong semantic target from overly broad literal deletion.
- **Identifier obfuscation 4/38; cross-lingual 1/38:** case-insensitive literal matching handles a few variants; it does not normalize separators/encodings or group transliterations. English BGE top-1 fallback is not identifier equivalence. These differ from the earlier 2/2 subsets, whose fixtures/configuration were not archived in this repo.
- Remaining failures: substring traps 10/36, paraphrases 8/38, negation 2/40, shared attributes 1/40, recursive supersession 3/39. Raw records expose forbidden-substring oracle collisions as well as incorrect mutation targets; a substring failure is not automatically proof of retained canonical state.
- **Graph residual:** supersede passes 5/5 top-k checks but fails all five full-row checks because a retained neighbor's inline `relations[].memory.content` exposes the invalidated source. Purge passes both surfaces 5/5. JIT-generated `entity:people:maya` tags were verified in all ten fixtures before relation/entity expansion; enrichment remained off during the separate 385-case baseline. These are small linked-neighbor probes, not a broad privacy guarantee or a MemLeak run.

## Policy and isolation

The adapter implements reset, inscribe, recall_texts (the Protocol's recall method), supersede, release, and purge. Mutations use server-recalled candidates: case-insensitive whole-query substring matches, otherwise top-1. Supersede uses the first selected source and composes POST /memory, PATCH t_invalid, POST /associate INVALIDATED_BY (old → new). Release sets t_invalid; purge hard-deletes. There is no gold-directed target selection, identifier router, compound planner, or paid inference.

The dedicated stack used AutoMem `3caa9d5`, local BGE-small 384d, no external API keys, and no enrichment/consolidation workers. Writes waited for vector-count synchronization before reads. Each case has a unique exact tag; reset deletes only tracked IDs. Final health was healthy, with zero memories/vectors. These cold English-embedder results do not estimate production Voyage or an agent's semantic mutation policy.

## Reproduce

Use a clean checkout of each pinned revision; the companion AutoMem source is read-only to containers. The runner verifies the exact AutoMem commit and clean working tree from the same exported `AUTOMEM_CHECKOUT` that Compose mounts, before contacting the API, and records `automem_checkout_revision` in new summaries. This is source provenance, not attestation of an independently started daemon; use the dedicated Compose service below for reproduction. The compose file starts new backend containers with no production volumes or credentials. Set `FORGETEVAL_PORT` to a free dedicated port if 18031 is occupied; both Compose and the adapter below use it.

```bash
git clone https://github.com/deeplethe/lethe.git /tmp/forgeteval-lethe
git -C /tmp/forgeteval-lethe checkout b6053b7bdacc78a91b9ea4bb25f32edad278c495
export AUTOMEM_CHECKOUT=/absolute/path/to/clean/automem-at-3caa9d5
export FORGETEVAL_RUN_ID=reproduction
export FORGETEVAL_PORT=18031
unset FORGETEVAL_JIT
docker compose -p forgeteval-reproduction -f scripts/benchmarks/forgeteval.compose.yml up -d --build
python3 scripts/benchmarks/forgeteval_automem.py --upstream /tmp/forgeteval-lethe --endpoint "http://127.0.0.1:$FORGETEVAL_PORT" --graph forgeteval-reproduction --output data/results/forgeteval-adv/reproduction
# Re-run only the extension after enabling local JIT entity extraction.
export FORGETEVAL_JIT=true
docker compose -p forgeteval-reproduction -f scripts/benchmarks/forgeteval.compose.yml up -d
python3 scripts/benchmarks/forgeteval_automem.py --upstream /tmp/forgeteval-lethe --endpoint "http://127.0.0.1:$FORGETEVAL_PORT" --graph forgeteval-reproduction --output data/results/forgeteval-adv/reproduction --diagnostics-only
docker compose -p forgeteval-reproduction -f scripts/benchmarks/forgeteval.compose.yml down -v
```

Wait for the API's /health endpoint before invoking the runner. A first run downloads the local embedding model; no paid embedding endpoint is selected. The second command keeps the original category artifacts/counts and refreshes only diagnostics. JSON artifacts include synthetic benchmark identifiers, not real customer credentials.

The [atomic-supersede proposal](../atomic-supersede-proposal.md) addresses the observed partial states. Semantic planning and inline relation suppression remain separate follow-ups. Experiment registry entry: `EXP-FORGETEVAL-ADV`.
