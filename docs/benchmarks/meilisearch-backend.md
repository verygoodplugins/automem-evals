# Meilisearch as an AutoMem retrieval backend (issue #83), slice 1

**Partial slice, no recommendation yet.** This PR has the keyword-leg adapter, pinned configs, an isolated stack and a
free cold LoCoMo retrieval-proxy harness, with baseline numbers. A Meilisearch arm did **not** complete, judged accuracy,
BEAM and matured runs were not run, and the vector-leg swap is deferred (see [Not done](#not-done-and-why)).
Nothing here is an official LoCoMo or BEAM score (`docs/REPO_BOUNDARY.md`).

## Built

| Piece | File |
|---|---|
| Meilisearch client, keyword-leg function, write mirror, `set_payload` handling | `scripts/benchmarks/meili_backend.py` |
| Arm installer = AutoMem container entrypoint (`MEILI_ARM`, `MEILI_KEYWORD_ONLY`) | `scripts/benchmarks/meili_launch.py` |
| LoCoMo probe, p50/p95/p99, RSS/disk probes, $20 spend gate | `scripts/benchmarks/meili_bench.py` |
| One-arm lifecycle on a fresh stack | `scripts/benchmarks/run_meili_arm.sh` |
| Isolated stack (ports 18001/16333/16379/17700), pins, seeds | `configs/meilisearch/` |

The launcher patches `runtime_recall_helpers._graph_keyword_search` and `qdrant_client.QdrantClient` before `app.py` imports
them; the scorer is untouched. Meilisearch ranks (query = AutoMem's `_extract_keywords`), FalkorDB hydrates nodes and relations,
and Qdrant upserts are mirrored into the index. Pinned: `getmeili/meilisearch:v1.56.1`, `PINNED_SETTINGS` (ranking rules, typo
tolerance, empty stop words, matching strategy `last`) are written into every Meilisearch result.

## Finding: the keyword leg is a fallback, not a blended channel

`recall.py` calls the keyword function only for slots the vector leg leaves empty (`remaining_slots`). On this workload
(419 memories, `limit=10`) it was called **0 times in 269 recalls**, so a default-path keyword swap cannot change accuracy
or latency. It matters only for under-filled recalls (small or tag-filtered sets). `KEYWORD_ONLY=1` forces the vector leg to
return nothing, which measures the leg itself.

## Results (LoCoMo `locomo10.json` conv 0, 419 turns, 149 gold-evidence questions, top-k 10, cold, local bge-small 384d)

**Caveat on every number below:** these runs predate blanking the provider keys. AutoMem loaded the mounted checkout's `.env`
itself, so its memory-type classifier called OpenAI (about one chat call per stored memory, outside any budget ledger, spend not
measured). Hit rates therefore include nondeterministic LLM classification, which may explain part of the 0.5235 vs 0.5369 spread.
`docker-compose.yml` now blanks `OPENAI_API_KEY` and `VOYAGE_API_KEY`; re-run for clean numbers before drawing conclusions.

| Arm | Hit rate | Cat 1 / 2 / 3 / 4 | Leg p50 / p95 / p99 ms (serial) | Ingest + drain | Cost |
|---|---|---|---|---|---|
| baseline, default `/recall` | 0.5369 | .42 / .54 / .36 / .61 | vector search 3.3 / 4.4 / 32.8 | 267 s | $0 |
| baseline, keyword leg only (Cypher) | 0.4497 | .23 / .65 / .27 / .47 | keyword 9.4 / 12.1 / 14.0 | 272 s | $0 |
| keyword_swap (Meilisearch), keyword only | **not completed** | | | | |
| vector_swap | **not run in this slice** | | | | |

End-to-end serial `/recall`: p50 59.7, p95 90.3, p99 93.0 ms (default). Under 8-way load the leg p50 rises (vector 41 ms,
keyword 127 ms) because the Docker VM CPU is shared with the local embedder, so treat load numbers as contention, not capacity.
Baseline RSS after ingest: Qdrant 404-408 MiB, FalkorDB 128-140 MiB, api 430-433 MiB. Qdrant data 6.1-6.8 MiB. An *unused* Meilisearch
container reads 239-304 MiB under `docker stats` (includes mmap/page cache), so footprint cannot be compared until a Meilisearch arm completes.
FalkorDB disk was not located (the reported 0.0 is not a measurement). Two default-baseline runs gave 0.5235 and 0.5369 (the first
did not wait for enrichment), so run-to-run noise is at least 1.3 points on 149 questions.

## Not done, and why

- **Meilisearch arm:** the keyword-only run stalled at 328 of 419 ingested turns and a 60 s harness call timed out. Meilisearch was
  healthy (1,157 tasks, 0 failed, mean 6.3 ms, index held all 328 documents), so the stall is server-side ingestion, cause unknown.
  Reproduce with `KEYWORD_ONLY=1 AUTOMEM_SRC=<automem@90f41af> scripts/benchmarks/run_meili_arm.sh keyword_swap`.
- **Vector-leg swap:** `MeiliQdrantShim` (Qdrant-API shim) is on side branch `agent/kernel-worker/96ffe1bf-vector-slice` (`ade745a`). It was
  exercised live against Meilisearch v1.56.1 and fixed for three bugs that the first runs exposed. The PR cap forced the split.
- **Judged accuracy (no judge spend):** the worker had no `OPENAI_API_KEY` of its own and `.env` reads were denied. Cap enforcement is
  `paid_budget_proxy.py` with one shared ledger plus the `meili_bench.py budget` projection gate; no paid call was made.
- **BEAM:** `beam_retrieval_eval.py` has no queue-drain wait between ingest and recall; wiring it did not fit.
- **Matured:** `maturation-v1` is unfrozen and unimplemented (`docs/eval/maturation.md`), `/consolidate` has no `reference_time`. Cold only.

## Caveats

One conversation, one run per arm: differences of a few points are noise. ThriveDesk's 2x speed and 9x memory claim is a different
workload and quality bar. Local embeddings differ from the Voyage-4 default, so absolute hit rates will move. Reproduce:
`AUTOMEM_SRC=<automem@90f41af> scripts/benchmarks/run_meili_arm.sh baseline`; tests: `python3.12 -m unittest discover -s scripts/benchmarks -p 'test_meili*.py'`.
