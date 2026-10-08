# EvalMem-style AutoMem diagnostic

Experimental operation attribution, not an official LoCoMo score. Candidate fingerprints: `opportunity:automem-graph-rag-research-scout` and `research:automem-evalmem-diagnostics`.

## Scope and attribution

[EvalMem](https://arxiv.org/html/2609.22231v1) diagnoses encoding, retrieval, and oracle-context generation independently, permits multiple labels, masks retrieval misses when storage lacks support, and gates reported defects on incorrect answers. Rates use **all evaluated queries**, not just failures. Its LoCoMo averages (retrieval 22.1%, encoding 7.7%, generation 6.5%) are paper references, never AutoMem measurements.

This first slice uses the official companion `automem` LoCoMo dataset/ingestion manifest: first five category-1 POS questions with resolvable evidence from `conv-26`. `EM` means the inspected bank lacks necessary support; `RF` means support exists but recall misses it; `GF`/`GRF` mean oracle generation ignores evidence/reasons incorrectly. Successful and unjudged answers contribute no labels. NEG, corrupt-value, ranking/noise subclasses, and LongMemEval are follow-up work; this is not a reproduction of the paper's full eleven-code protocol.

Encoding observes every manifested record through `GET /memory/<id>`, with conversation/dialog/tag validation; the judge sees that complete bank, independently of native retrieval. A stale/incomplete manifest produces unknown encoding and `not_scored`, never an inferred absence. Completeness is relative to the manifested bank; unmanifested summaries are outside scope. Gold/oracle evidence is supplied only to the examiner and separate oracle generator, never native generation or graph selection. JSON records contexts, answers, examiner states/reasons, model usage, prompts, and source/bank hashes.

Graph-off uses `/recall` with `expand_relations=false`. Graph-on reuses exactly that response and the existing `client_side_expand` one-hop traversal (typed edges, strength >=0.6, at most three per seed), accepts only manifested targets, and adds at most `--limit` records. Identical contexts reuse judgments to remove sampling confounds. This is an additive context-budget intervention, not an equal-token comparison; a full study needs budget controls. The diagnostic issues only GETs to AutoMem; normal server recall may update access/enrichment metadata.

## Reproduce

From this eval checkout, point to the canonical companion; keep its official dataset and matching ingestion manifest together. For a fresh stack, use its documented `tests/benchmarks/test_locomo.py --conversations 0 --ingest-only` flow first (embedding calls may cost money). The live pilot reused an existing store; no ingestion, deletion, maintenance, or companion edits were performed.

```bash
export AUTOMEM_DIR=/path/to/automem
python3 scripts/benchmarks/evalmem_diagnostic.py \
  --dataset "$AUTOMEM_DIR/tests/benchmarks/locomo/data/locomo10.json" \
  --offline --output data/results/evalmem/offline-smoke.json
# Live read-only retrieval + optional paid answer/judge (OPENAI_API_KEY):
python3 scripts/benchmarks/evalmem_diagnostic.py \
  --dataset "$AUTOMEM_DIR/tests/benchmarks/locomo/data/locomo10.json" \
  --model --questions 5 --limit 5 --output data/results/evalmem/locomo-five.json
```

Omit `--model` for live heuristic mode. `--offline` performs no HTTP/model calls. Missing credentials, incomplete bank, invalid examiner output, or unavailable judge leave rates null (`not_scored`). `--model` defaults to the repo's pinned `gpt-5.4-mini-2026-03-17`; the same model answers and judges, so a funded run needs human spot-checks. AutoMem defaults to localhost:8001 and `test-token`; override token through `AUTOMEM_API_TOKEN`. Remote AutoMem endpoints are rejected. No public leaderboard submission occurs.

## Pilot: 2026-10-08

[Measured artifact](../../data/results/evalmem/locomo-five.json): five questions, 419/419 stored records verified, existing ingestion scope `locomo-automem-c11378d4b8:conv-26`. The configured OpenAI key could list the model, but completion calls returned **429 `credit_balance_exhausted`**. No answer or semantic judgment completed. Both arms are `not_scored`.

| Arm | Encoding defect rate | Retrieval defect rate | Generation defect rate |
| --- | --- | --- | --- |
| Graph off | null (unjudged) | null (unjudged) | null (unjudged) |
| Graph on | null (unjudged) | null (unjudged) | null (unjudged) |

Root-cause note: all eight annotated evidence-turn incidences were stored, but only one appeared in native top-five recall; none of the five questions retrieved every annotated turn. Alternate records may still supply usable facts, so this cannot establish retrieval defects. Graph traversal added **zero records** across all five questions. Retrieval-defect reduction is **null**, not zero: no semantic score exists and this pilot did not exercise a useful graph intervention. The store is pre-existing with unknown maturation history; these observations are neither cold nor matured benchmark results.

**Recommendation: NO-GO for a full scored run.** Fund/validate the judge, spot-check evidence sufficiency, freeze a reproducible store snapshot, and verify traversable in-scope edges before a larger stratified, budget-controlled run. GO for reviewing this diagnostic slice and offline smoke.

## Verification report / PR handoff

Commands and captured output on this branch (the repo has no single universal test command):

```text
python3 -m unittest discover -s runners -p 'test_*.py'
Ran 233 tests; OK (skipped=13)
python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 30 tests; OK
python3 -m unittest discover -s scripts/benchmarks -p 'test_*.py'
Ran 16 tests; OK
uv run --with pytest --with pyyaml --with requests python -m pytest tests/matrix/ -q
12 passed
python3 -m py_compile scripts/benchmarks/evalmem_diagnostic.py scripts/benchmarks/test_evalmem_diagnostic.py
exit 0
offline smoke: graph_off/graph_on status=not_scored, queries=5, rates=null
live --model smoke: bank_records=419, bank_complete=true; HTTPError 429
graph_off/graph_on status=not_scored, queries=5, rates=null; added_graph_records=0
```

Duplicate check covered open/closed issues and PRs before implementation: no EvalMem match. [DolphinBench #45](https://github.com/verygoodplugins/automem-evals/issues/45) / [PR #46](https://github.com/verygoodplugins/automem-evals/pull/46) cover task completion; [A-TMA #57](https://github.com/verygoodplugins/automem-evals/issues/57) / [PR #58](https://github.com/verygoodplugins/automem-evals/pull/58) track artifact-blocked ghost-memory evaluation. Neither is duplicated. Official claims remain in `automem` per [repo boundary](../REPO_BOUNDARY.md). Copy this verification evidence and NO-GO recommendation into the orchestrator-created PR; this worker commits locally without pushing or opening a PR.
