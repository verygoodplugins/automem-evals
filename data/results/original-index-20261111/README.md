# Original-text retrieval: isolated diagnostic comparison

These results include candidates `a5d5c1e`, `e3a3e3d`, `b83d349`, `b3beabc` and `6ea4470`. The last candidate is the table column below; no result establishes the behavior of a later PR head. This is an exploratory retrieval experiment, not an official LoCoMo score, answer-quality test, or production benchmark. No paid provider calls or production data were used. Baseline `1a7ba1a6afe69835f62ad7f6013e33301d1ab83e` and candidate `6ea44702c161a1bda7dabd27d5bde20ab63a6881` were run in separately created, destroyed Docker projects with internal networks, the same local BGE model, and the identical fixture hash `d89af992a8e71bc2aafde8ba54fdb441e93b6b716de63bc9cc1a57b0b64559f6`. The product changes between them implement original-text preservation, backfill and recall, with follow-up ranking and state-accounting corrections. All five candidates had the same reported retrieval counts; each run is retained in aggregate JSON. Relation expansion was disabled throughout, so the latest graph-expansion fix is covered by its product regression test rather than this benchmark. The fixed query parameters include exact tag scope, `limit=10`, disabled relation expansion, and `current_only` except for the historical probes. Scores below use `min_score=0`; the fixed 0.4 control is discussed separately.

| Held-out probe | Baseline | Candidate after explicit trusted backfill | Chunk prototype |
| --- | ---: | ---: | ---: |
| Buried identifier, R@1 (16) | 2 | 16 | 12 |
| Buried identifier, R@5 (16) | 10 | 16 | 16 |
| Buried paraphrase, R@5 (16) | 14 | 14 | 14 |
| LoCoMo all labelled evidence @5 (136) | 58 | 62 | 77 |
| LoCoMo all labelled evidence @10 (136) | 69 | 75 | 100 |
| Literal/Unicode/path controls, R@1 (4) | 1 | 4 | 4 |
| 300-distractor unique marker | absent from top 10 | rank 1 | rank 1 |
| Negative query returned any result (16) | 16 | 16 | 16 |
| Wrong-scope query returned any result (4) | 4 | 4 | 4 |
| Current-only expired/future leaks (8) | 0 | 0 | 0 |
| Expired evidence found with history enabled (4) | 4 | 4 | 4 |

Counts are out of the query counts in parentheses. All runs had zero observed cross-scope results, including wrong-scope queries: the nonempty results there were unrelated in-scope memories. The negative result rate measures nonempty responses, not incorrect downstream answers. LoCoMo is a public evidence-labelled slice: labels do not exhaust all relevance and all-evidence coverage is not the official answer score. Its 136 queries use 154 records, and the source adapter reports 71 adversarial, 94 visual-evidence and 3 unresolvable questions excluded. The fixture includes 548 records overall and 205 distinct queries; 52 synthetic query/floor pairs are repeated at 0.4, for 257 server probes. See machine-readable source exclusions and per-question ranks in the JSON files.

The paired @5 change is +6 / -0 identifiers and +4 / -0 LoCoMo queries; paraphrases are +0 / -0. In the 16 topical negatives, `min_score=0.4` reduced nonempty results to 2 for both server revisions, but also removed all 16 paraphrase targets for both. It removed all identifier targets in baseline but none after trusted backfill. This fixed threshold was not optimized, and should not be interpreted as an acceptable production threshold. Querying an old term after PATCH still returned the updated memory through vector similarity even though the old term no longer existed in the original-text index; a nonempty result is not necessarily obsolete content.

## Backfill and index maintenance

All 548 records were created by the old server with preserved originals in metadata. On candidate startup, the identifier R@5 was 10/16. Dry run reported 548 unverified originals and applied zero writes. The conservative apply indexed the stored current content for all 548; identifier R@5 remained 10/16. With explicit `--assume-legacy-original-current`, 542 records were upgraded to preserved originals and six already matched their current content. Read-only verification found all 548 labels and index properties present, no conflicts or mismatches; repeating the trusted apply made zero changes. This opt-in is a synthetic experiment, not authorization to trust unknown production history. Old batch originals that were never preserved cannot be recovered by any backfill.

One controlled record was PATCHed and deleted after the retrieval measurements. Direct native full-text queries confirmed that its old marker disappeared on PATCH, its new marker appeared, and the new marker disappeared on DELETE. The patch's old query continued to return the updated memory through the vector channel at floor 0; the native index did not retain the old marker. This is a precision limitation, not proof of stale original-text leakage.

The latest candidate conservative write took 1,466 ms and trusted upgrade 1,314 ms for this small local graph; these wall times include command startup and are not production estimates. Total original text was 195,215 UTF-8 bytes; this is not the measured index or disk footprint. The prototype created 966 768-dimensional float32 chunk vectors (2,967,552 raw bytes excluding index/storage overhead), using 60-word chunks with 10-word overlap; the batch embedding/index phase took 94.5 seconds on a shared host. Its latency is CPU-only scoring of already embedded queries, whereas server latency includes HTTP, query embeddings, and server retrieval. They cannot be compared. Server LoCoMo query p50/p95 were 132/175 ms baseline and 227/310 ms latest candidate, measured sequentially under variable host load; these do not establish a latency improvement.

Paired comparison of `b83d349` and optimized `b3beabc` found identical first- and all-evidence ranks across all 257 query/floor pairs. One top-10 list changed: the stress target stayed at rank 1 but the nine distractors differed. Overall query p50/p95 were 119/180 ms and 223/424 ms, respectively. These sequential measurements were made under variable shared-host load; backfill timings also rose substantially, so they do not isolate the optimization or establish a performance regression. Both servers used the same fixture and model.

Paired comparison of `b3beabc` and `6ea4470` also preserved first- and all-evidence ranks across all 257 probes. One stress-query list changed distractors, with the target still first. Overall p50/p95 were 223/424 ms and 204/300 ms, respectively; separate sequential runs under shared-host load cannot establish a performance effect. The suite does not exercise the replacement-relation path changed in this commit.

The chunk arm is an exhaustive client-side prototype with max cosine and summary BM25, not an AutoMem implementation or matched server ranking. It suggests chunk vectors deserve a proper controlled system experiment, not that their apparent gain is deployable. The LoCoMo construction also simulates summarized memories: these are public dialogue snippets with fixture-provided short summaries, not a representative measurement of actual summarizer quality. The small synthetic controls are deliberately diagnostic, not a population sample. No agent answer success, context-token, no-memory, or raw-history controls were measured.

## Artifacts and reproduction

- `aggregate.json`: reviewed aggregate metrics, pinned model and image revisions, backfill counts, and hashes of local run outputs.
- The uncommitted local run outputs `baseline.json`, `candidate.json`, `candidate-e3a3e3d.json`, `candidate-b83d349.json`, `candidate-b3beabc.json`, `candidate-6ea4470.json`, `chunk-prototype.json` and the `comparison` files contain per-query rankings and can be regenerated. They are excluded from the published artifacts in line with the repository data policy.
- Harness and pinned LoCoMo adapter: `experiments/original_index_eval/`.

Use a clean checkout for each pinned server revision, the cached BGE model, the pinned LoCoMo dataset, and the project's Python environment. Example commands (the explicit trusted backfill is invoked only inside a newly created disposable Docker project):

```sh
python experiments/original_index_eval/run_server.py --mode baseline --baseline /path/to/baseline-automem --dataset /path/to/locomo10.json --cache-dir /path/to/local/models --output data/results/original-index-20261111/baseline.json
python experiments/original_index_eval/run_server.py --mode candidate --baseline /path/to/baseline-automem --candidate /path/to/candidate-automem --dataset /path/to/locomo10.json --cache-dir /path/to/local/models --output data/results/original-index-20261111/candidate.json
python experiments/original_index_eval/chunk_prototype.py --help
python experiments/original_index_eval/compare.py data/results/original-index-20261111/baseline.json data/results/original-index-20261111/candidate.json data/results/original-index-20261111/chunk-prototype.json data/results/original-index-20261111/comparison.json
python -m unittest discover -s experiments/original_index_eval -p 'test_*.py' -v
```
