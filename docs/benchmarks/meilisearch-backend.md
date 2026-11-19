# Meilisearch as an AutoMem retrieval backend (issue #83): keyword leg on LoCoMo

**Partial, recommendation provisional.** Keyword-leg swap, cold, LoCoMo `locomo10.json` conv 0 (419 turns, 149 gold-evidence
questions, top-k 10), retrieval proxy only: no LLM judge, **$0 of the $20 cap spent**. Vector leg, BEAM, matured and judged runs
are not in this PR (see [Not in this PR](#not-in-this-pr)). Nothing here is an official LoCoMo or BEAM score (`docs/REPO_BOUNDARY.md`).

## Built
`meili_backend.py` (client, keyword-leg function, write mirror), `meili_launch.py` (arm installer / container entrypoint),
`meili_bench.py` (probe, p50/p95/p99, RSS/disk, spend gate), `run_meili_arm.sh` (one arm on a fresh stack), `configs/meilisearch/`
(isolated ports 18001/16333/16379/17700, pins, seeds). The launcher patches `_graph_keyword_search` and `QdrantClient` before
`app.py` imports them; the scorer is untouched. Meilisearch ranks, FalkorDB hydrates, Qdrant upserts are mirrored into the index.
Pinned: `getmeili/meilisearch:v1.56.1`, `PINNED_SETTINGS` (ranking rules, typo tolerance, empty stop words), AutoMem `90f41af`,
local `bge-small-en-v1.5` 384d embeddings in every arm. Effective settings are written into each result file.

## Corrections to slice 1
- **The "ingest stall" and every slice-1 number are retracted.** AutoMem loads the mounted checkout's `.env`, and the memory-type
  classifier (`automem/api/memory.py:584`) can call OpenAI from the `/memory` store path, unbudgeted. With provider keys blanked
  (compose now does) 419 turns post in about 2 s and drain in 7-24 s with no stall, and baseline default moves **0.5369 -> 0.6711**.
  Tracing the stalled run was not repeated, so the classifier is the likely cause, not a proven one.
- `run_meili_arm.sh` was committed non-executable; fixed.

## Results (clean, one run per arm)
| Arm | Hit rate (cat 1/2/3/4) | Keyword leg p50/p95/p99 ms | `/recall` p50/p95/p99 ms | Ingest+drain s | Meili RSS idle/load MiB |
|---|---|---|---|---|---|
| baseline, default | **0.6711** (.55/.84/.55/.66) | 0.7/1.6/1.6 (12 calls) | 57.2/84.3/92.9 | 7.2 | n/a |
| keyword_swap `last`, default | **0.6711** (identical) | 0.9/2.0/2.0 (12 calls) | 66.7/100.9/129.0 | 20.8 | 683/619 |
| baseline, keyword only (Cypher) | 0.4631 (.23/.65/.36/.49) | 8.4/9.8/10.4 | 39.9/67.8/74.6 | 10.5 | n/a |
| keyword_swap `last`, keyword only | 0.0604 (.03/.08/.00/.07) | 7.8/10.4/13.7 | 41.8/72.5/85.5 | 24.2 | 651/692 |
| keyword_swap `frequency`, keyword only (post-hoc) | 0.3960 (.26/.73/.09/.33) | 2.4/7.1/7.7 | 31.1/57.6/68.1 | 22.2 | 687/731 |

Other containers are the same in every arm: api ~460 MiB, Qdrant ~400, FalkorDB ~200 (idle, `docker stats`); an unused Meilisearch
container reads 245. Disk: Qdrant 4.7-5.0 MiB, Meilisearch index 11.3-11.5 MiB (FalkorDB disk reads 0.0: path not found, not a
measurement). Cost is $0 for every arm: local embeddings, self-hosted, no provider calls. Load (8 workers) numbers mostly measure
Docker VM CPU contention with the local embedder; they are in the result files.

## Findings
1. **Default path: no accuracy change.** Per-category hits are identical because the keyword leg only fills slots the vector leg
   leaves empty (`recall.py` `remaining_slots`): called for 12 of 149 recalls, none moved a top-10 hit.
2. **`matchingStrategy: last` (Meilisearch default, pinned a priori) collapses on question-form queries.** AutoMem's extractor leaves
   "did" first (`["did","caroline","lgbtq","support","group"]`) and `last` never drops the first term. Querying the live index
   directly with the real extractor reproduced 0.0604 exactly, so the adapter is not the cause. `frequency` (drops the most common
   terms first) gives 0.3960. **It was chosen after seeing `last` fail, on the same 149 questions, so treat it as exploratory.**
3. **Leg speed:** Meilisearch keyword leg is about 3.5x faster than Cypher `CONTAINS` at p50 (2.4 vs 8.4 ms) on 419 documents.
   End-to-end `/recall` is mostly query-embedding time, so nothing user-visible changes at this scale.
4. **Memory and ingest go the wrong way for a leg swap:** Meilisearch adds about 650-730 MiB (includes LMDB mmap) on top of Qdrant
   and FalkorDB, which stay, and ingest drain is 2-3x slower because each mirrored write waits for its Meilisearch task. ThriveDesk's
   "9x less memory" does not show here; their workload and quality bar differ.

**Provisional recommendation: do not adopt for the keyword leg.** No accuracy upside on the default path, keyword-only `frequency`
is 6.7 points below Cypher (cat 3: 0.09 vs 0.36, n=11) on 149 questions, and memory and ingest cost rise. A final adopt / keyword-only
/ drop call needs the vector-leg, BEAM, matured and judged runs below.

## Not in this PR
- **Vector-leg swap and BEAM 100K driver:** stacked branch `agent/kernel-worker/96ffe1bf-slice3` (PR cap forced the split).
- **Judged accuracy:** the worker has no `OPENAI_API_KEY` and `.env` reads are denied. This is a key problem, not a cap problem.
  The gate (`meili_bench.py budget`, shared ledger in `paid_budget_proxy.py`) is in place; no paid call was made.
- **Matured runs:** `maturation-v1` is unfrozen and unimplemented (`docs/eval/maturation.md`); cold only.
- One conversation, one run per arm: differences of a few points are noise (two earlier runs differed by 1.3 points).

Reproduce: `AUTOMEM_SRC=<automem@90f41af> [KEYWORD_ONLY=1] [MEILI_MATCHING_STRATEGY=frequency] scripts/benchmarks/run_meili_arm.sh baseline|keyword_swap`;
tests: `python3.12 -m unittest discover -s scripts/benchmarks -p 'test_meili*.py'`.
