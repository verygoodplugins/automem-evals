# Meilisearch as an AutoMem retrieval backend (issue #83)

Status: **partial slice.** Adapter, configs and a free cold LoCoMo retrieval-proxy comparison are here.
Judged accuracy, BEAM, and matured runs are **not run** (see [Not run](#not-run-and-why)). Nothing below is an
official LoCoMo or BEAM score. Official claims stay in `automem` (`docs/REPO_BOUNDARY.md`).

## What was built

| Piece | File |
|---|---|
| Meilisearch client, keyword-leg function, Qdrant-API shim, write mirror | `scripts/benchmarks/meili_backend.py` |
| Arm installer run as the AutoMem container entrypoint (`MEILI_ARM`) | `scripts/benchmarks/meili_launch.py` |
| LoCoMo probe, p50/p95/p99, RSS and disk probes, $20 spend gate | `scripts/benchmarks/meili_bench.py` |
| One-arm lifecycle (fresh stack, run, teardown) | `scripts/benchmarks/run_meili_arm.sh` |
| Isolated stack (offset ports 18001/16333/16379/17700), pins, seeds | `configs/meilisearch/` |

Swaps use AutoMem's existing seams and leave the scorer untouched. The launcher patches
`runtime_recall_helpers._graph_keyword_search` and `qdrant_client.QdrantClient` before `app.py` imports them.
Qdrant methods the shim does not implement raise instead of falling back, so an arm cannot silently measure Qdrant.

- **keyword_swap:** Meilisearch ranks (query = AutoMem's own `_extract_keywords`), FalkorDB hydrates nodes and relations. Writes are mirrored from the Qdrant upsert path. Qdrant vectors, graph, tags and recency are unchanged.
- **vector_swap:** `MeiliQdrantShim` serves search/upsert/retrieve/scroll/delete/set_payload from one Meilisearch index (`userProvided` embedder, `semanticRatio` 1.0). Scores are recomputed as exact cosine so they match Qdrant's scale and the blended scorer is unchanged. Pure vector, not hybrid, so the keyword leg stays FalkorDB.

## Method

LoCoMo `locomo10.json` conversation 0 (419 turns, non-adversarial questions with gold evidence), one turn per memory, top-k 10.
Hit = a gold evidence turn is in the top-k. Local `bge-small-en-v1.5` (384d) embeddings, identical for every arm.
Cold = ingest, drain embedding and enrichment queues, recall; no consolidation. Each arm runs on a fresh stack.
Latency has two views: end-to-end `/recall` (serial) and store-side leg latency timed in-process, because local CPU
query embedding (about 0.8 s) is identical across arms and would hide any store difference.
Footprint counts only containers the arm uses: baseline = qdrant + falkordb, keyword = qdrant + falkordb + meilisearch,
vector = falkordb + meilisearch. `flask-api` is reported separately.

Reproduce: `AUTOMEM_SRC=<automem@90f41af> scripts/benchmarks/run_meili_arm.sh baseline|keyword_swap|vector_swap`.
Unit tests: `python3.12 -m unittest discover -s scripts/benchmarks -p 'test_meili*.py'`.

<!--RESULTS-->

## Not run, and why

- **Judged accuracy ($0 of $20 spent):** the worker had no `OPENAI_API_KEY` (not in its environment; `.env` reads were denied). The $20 cap is enforced by `paid_budget_proxy.py` with one shared ledger, and `meili_bench.py budget` gates the projection, but no paid call was made, so there is no measured per-run cost to project from.
- **BEAM:** `beam_retrieval_eval.py` has no queue-drain wait between ingest and recall, and wiring it for three arms did not fit this PR's size budget. Follow-up slice.
- **Matured:** `maturation-v1` is unfrozen and unimplemented (`docs/eval/maturation.md`), and `/consolidate` takes no `reference_time`. An ad-hoc profile would break the frozen-profile rule, so none was used. Cold is the only fully wired mode.
- **Not covered:** the consolidation and backup paths call more Qdrant methods than recall does; the shim implements them but they were not exercised live.

## Caveats

- Single conversation, single run per arm: differences of a few points are within noise. Use these as a smoke signal, not a verdict.
- ThriveDesk's 2x speed and 9x memory claim is not comparable (different workload and quality bar). This workload is 419 memories, far smaller than production.
- Local embeddings differ from the Voyage-4 production default; absolute hit rates will move with the embedder.
