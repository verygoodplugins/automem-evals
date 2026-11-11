# Synthetic graph expansion diagnostic — 2026-11-11

This diagnostic is a small, hand-authored **retrieval** probe, not an agent task benchmark or a general estimate of graph value. It uses 23 synthetic memories, six associations and six queries: one direct fact, two linked facts, a neighboring different project, a negative query, and current and historical views of a changed fact. It runs each query at limits 5 and 10 with expansion off/on and `expand_respect_tags` true/false (48 requests). All other request settings, corpus, embeddings, and a client-side 200-word context budget are shared. Model, fixture, source and image hashes are in [aggregate.json](aggregate.json).

| Limit | Respect tags | Expansion | All expected at top-k (5 positive queries) | All expected in budgeted context (5) | Off-label top-level results (6 queries) | Foreign top / inline | Current stale top / inline | Total response bytes (6 requests) |
|---:|:---:|:---:|---:|---:|---:|---:|---:|---:|
| 5 | yes | off | 4 | 5 | 8 | 0 / 1 | 0 / 0 | 19,164 |
| 5 | yes | on | 4 | 5 | 8 | 0 / 1 | 0 / 0 | 21,029 |
| 5 | no | off | 4 | 5 | 8 | 0 / 1 | 0 / 0 | 19,164 |
| 5 | no | on | 4 | 5 | 9 | 1 / 1 | 0 / 0 | 22,204 |
| 10 | yes | off | 4 | 5 | 13 | 0 / 1 | 0 / 0 | 23,933 |
| 10 | yes | on | 4 | 5 | 13 | 0 / 1 | 0 / 0 | 25,798 |
| 10 | no | off | 4 | 5 | 13 | 0 / 1 | 0 / 0 | 23,932 |
| 10 | no | on | 4 | 5 | 14 | 1 / 1 | 0 / 0 | 26,973 |

The off-label count includes every top-level result outside a scenario's explicitly labeled expected set; it is not an exhaustive human relevance judgment. The one negative query returned two unrelated top-level memories in every arm (`min_score=0`). The historical query correctly made its old memory available, and no stale content was observed for the current query in these fixtures.

In the linked-fact case, expansion returned **6 and 11 top-level rows** for requested limits 5 and 10 respectively, placing the added linked target after the requested cutoff. This overflow is reported in the full API response but excluded from the matched client top-k score. The existing inline relationship already supplied both facts within the context budget with expansion off, so this probe shows no gain in either capped top-k or budgeted evidence. It does not establish that graph expansion lacks value elsewhere.

The project-scoped query returned the foreign neighbor's content inline in every arm, including expansion off and `expand_respect_tags=true`; the response's tag gating therefore did not constrain that inline relationship in this reproduction. This finding concerns retrieval scope, not an established authorization boundary. With expansion on and tag respect explicitly disabled, the foreign neighbor was also returned as a top-level result, which is consistent with the disabled setting. The inline issue and limit overflow warrant product regressions and fixes; neither should be attributed to graph expansion generally without further tests.

Context is measured by traversing the first k returned results in order and their inline relations, accepting whole content/summary segments until a shared 200 **whitespace-word** budget; it excludes metadata and tags and is not a model tokenizer or a measurement of actual agent context construction. Foreign and stale inline counts use only segments that fit this budget. Response bytes are full untrimmed HTTP JSON bodies and include fields outside that budget; the row-level aggregate includes observational elapsed times, which should not be compared as reliable performance benchmarks from this tiny sequential run. Last-access updates were disabled and a graph snapshot of every memory's `last_accessed` was identical before and after all requests. Enrichment, consolidation and synchronization were disabled.

## Reproduction

Run on a machine with Docker, the cached BGE model and the pinned local images listed in the aggregate. The `latest` image tags are mutable: compare `docker image inspect` IDs with those in the receipt before treating another run as comparable. The harness archives only product commit `46481560b6bf8570a7a43fc1d7e2a5bfdae4e236`, checks its own committed source, creates a uniquely named internal-only Compose project with no exposed ports, and removes that project's containers, network and volumes on exit. The local model runs offline; no paid provider is used.

```sh
python3 -m unittest discover -s experiments/graph_value_probe -p 'test_*.py' -v
python3 experiments/graph_value_probe/run.py \
  --product-repo /path/to/automem \
  --model-cache /path/to/automem/models \
  --output /tmp/graph-value-new-run.json
```

The runner emits a local aggregate plus a sibling `-raw.json` receipt with synthetic fixture IDs, every exact query parameter (including embedding vectors), and untrimmed response envelopes. The original receipt is `/tmp/automem-graph-value-20261111-run03-raw.json`, SHA-256 `39e5111fb92e2093632668c2e26fe8419dc898a45828e953880bd35c08f5a288`; those IDs apply only to its now-deleted stack. To reproduce either finding, inspect the `scope` and `linked` queries in `scenario.py` and their corresponding request envelopes in a new local raw receipt. The committed aggregate contains no raw trace. The run used runner revision `ed86a2aa8ca38ae56d63e8fc082d217b61e5a735`; the API log scan found zero lines matching its error patterns and cleanup completed.
