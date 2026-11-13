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

## Paired product-fix probe

A separate pair of disposable, internal-only stacks repeated the same 48 request shapes against product `46481560b6bf8570a7a43fc1d7e2a5bfdae4e236` and the **intermediate combined** scope-and-limit candidate `4d1110b448ecccea6fc1967d104cb983177a485d`. Both used the same fixture hash, local embedding model, image IDs, settings and 200-word budget; neither called a paid provider. Each API log scan found zero matching error lines, and both access snapshots were unchanged. See [paired-fix-aggregate.json](paired-fix-aggregate.json) for counts and provenance.

| Measure | Before | Intermediate combined candidate |
|---|---:|---:|
| Requests with foreign inline content, tag respect on | 4 / 24 | 0 / 24 |
| Requests with foreign inline content, tag respect off | 4 / 24 | 4 / 24 |
| Requests exceeding the requested top-level result limit | 4 / 48 | 0 / 48 |
| Positive request variants with all expected evidence at client-capped top 5 | 32 / 40 | 32 / 40 |
| Positive request variants with all expected evidence in budgeted context | 40 / 40 | 40 / 40 |
| Negative request variants returning any result | 8 / 8 | 8 / 8 |

The variants repeat the same five positive and one negative synthetic queries across limits, expansion settings and tag-respect settings; they are not 40 independent examples. The only overflow instances were the linked query with expansion on, where raw counts fell from 6 to 5 at limit 5 and 11 to 10 at limit 10. Tag-respecting scope requests no longer exposed the foreign neighbor's content inline, including when expansion was off. With tag respect explicitly off, the behavior was unchanged. The negative query continued to return two unrelated results at `min_score=0`; neither fix addresses that precision issue. No current stale top-level or budgeted inline content was observed, and the historical expected evidence remained available in every variant. The measurements do not establish an authorization boundary or agent answer quality.

This was a test of the combined *intermediate* revision, not of either final PR head in isolation. Docker stopped before a final-head replay; the later replay below addresses that gap for the combined changes only. The required broader benchmarks are separate.

The paired receipts identify repository runner revision `e8fc6d08c11f4d2ee6eae4f4e3b25ff43a02369b`, but their `runner_files.run.py` hash is the unchanged repository file, **not** the executed temporary copy. That copy had SHA-256 `ed77faffa14a30fee58c38d8895a28d0041560c7cc42bab5bb903c49aad15074` and differs in two lines: its `HERE` points at the repository's runner directory, and `PRODUCT` reads `GRAPH_PRODUCT_SHA` instead of the fixed baseline. The scenario and server source hashes match the recorded files. The private local paired receipts and their full synthetic responses are `/tmp/graph-value-comparison-{before,after}-20261111.json` and their `-raw.json` siblings; these are separate from the original baseline receipt below. The committed reproduction runner itself pins the baseline and cannot reproduce the candidate without an equivalent product selection change.

## Final combined replay — 2026-11-13

Two fresh internal-only stacks compared baseline `46481560b6bf8570a7a43fc1d7e2a5bfdae4e236` with integration commit `3f9a4241c8932068b31dd658c885262b247a73f1`, made by applying the exact scope PR head `092b3d8023cbe334153586fc6e683e826e511db6` to limit PR head `8c120b1d10f9478c4a188b482933f7ceac028e5f`. This tests the changes **together**, not each standalone PR or a merge result. The integration's two scope commits cherry-pick `f9670444ba9b963335b92a89a7e3021d95f3be0a` and `092b3d8023cbe334153586fc6e683e826e511db6`; recreating the cherry-picks may produce different commit IDs. The pair used the same six synthetic queries, 23 memories, six relations, settings, local BGE model and 200-word budget as above. Both API log scans found zero matching error lines, access snapshots were unchanged, and both stacks were removed. No paid provider was used.

| Measure | Baseline | Combined final heads |
|---|---:|---:|
| Requests with foreign inline content, tag respect on | 4 / 24 | 0 / 24 |
| Requests with foreign inline content, tag respect off | 4 / 24 | 4 / 24 |
| Requests exceeding the requested top-level limit | 4 / 48 | 0 / 48 |
| Positive request variants with all expected evidence at client-capped top 5 | 32 / 40 | 32 / 40 |
| Positive request variants with all expected evidence in budgeted context | 40 / 40 | 40 / 40 |
| Negative request variants returning any result | 8 / 8 | 8 / 8 |

The 48 variants repeat six queries across four settings and two limits; they are not 48 independent examples. The negative query still returned unrelated results at `min_score=0`; sampled current results had no observed stale content and historical evidence was available. The scoped inline count concerns content within the defined budget, not an authorization guarantee. No agent answers were measured. See [final-replay-aggregate.json](final-replay-aggregate.json) for matching image, fixture, model and executed-runner hashes. Raw synthetic envelopes and full receipts remain local.

The exact executed [replay runner](replay-20261113.py) is archived for inspection; its SHA-256 is `798069625fa0a61211bb3c8bb74cb2bf701e96f959b7fd4bf0339c1b7f4a8036`. It pins both product commits and the evaluation revision `37ca06f70ae3e92b818b70d5fc1ae672db944fb0`, uses an absolute local evaluation checkout path, and expects `scenario.py`, `server.py` and `compose.yaml` beside it. Replaying exactly therefore requires that evaluation checkout at that revision and local path, those sibling files from that revision, both product commits, the model and matching image IDs. Editing the path or choosing a newly reconstructed integration commit changes the executed script hash and must be recorded as a new run. The local receipts are `/private/tmp/graph-value-final-replay-20261113/{baseline,combined}.json` with sibling `-raw.json` files; the aggregate reports their raw hashes. The local comparison script checked matching model, image, fixture and runner hashes, 48 distinct request shapes, clean API logs and unchanged access snapshots; its SHA-256 is `1b1a270186a71c5306cadf6236399097736f55cbc9a595e262f2618591fd0acf`.

The script hashes its sibling `run.py`, so do not execute it under the archived filename or overwrite an existing runner. Copy it as `run.py` into a new directory with the three pinned sibling files, then verify its hash before running. For example, from this checkout:

```sh
replay_dir=$(mktemp -d "${TMPDIR:-/tmp}/graph-replay.XXXXXXXX")
cp data/results/graph-value-probe-20261111/replay-20261113.py "$replay_dir/run.py"
for file in scenario.py server.py compose.yaml; do
  git show "37ca06f70ae3e92b818b70d5fc1ae672db944fb0:experiments/graph_value_probe/$file" > "$replay_dir/$file"
done
shasum -a 256 "$replay_dir/run.py"
```

The last command must print `798069625fa0a61211bb3c8bb74cb2bf701e96f959b7fd4bf0339c1b7f4a8036`. The pinned absolute checkout must independently exist at revision `37ca06f` before either arm will run; setting up that checkout must not overwrite an existing worktree. After verifying the prerequisites, run each arm in sequence with new output paths:

```sh
python3 "$replay_dir/run.py" --product-repo /path/to/automem --model-cache /path/to/automem/models --arm baseline --output "$replay_dir/baseline.json"
python3 "$replay_dir/run.py" --product-repo /path/to/automem --model-cache /path/to/automem/models --arm combined --output "$replay_dir/combined.json"
```

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
