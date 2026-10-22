# Post-merge baseline: 22 October 2026

The merged system fixes several write-path correctness defects. ForgetEval, PMB and graph suites show **no assertion regressions or pass-count gains**; targeted tag checks improve **20/22 to 22/22**. Inline superseded content still appears in recall relations, making response-envelope lifecycle filtering the next product fix. Paid answer-quality evaluation is **incomplete**: OpenAI rejected preflight calls with HTTP 429 before any benchmark question ran. No new LoCoMo or LongMemEval score is publishable.

## Frozen comparison and evidence

| Item | Frozen value |
| --- | --- |
| Control server | `01a17aa38e678924c07a51015ef705b8474e2193` |
| Candidate server | `3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876` |
| Official harness, both arms | Candidate SHA above; source checkouts remained clean |
| Eval harness base | `35fa73d78703b4af6387762df7b74884520dc29f` |
| ForgetEval adapter / upstream | `4723034d2d5fe7a29f448ee4fed9d93e838c2724` / Lethe `b6053b7bdacc78a91b9ea4bb25f32edad278c495` |
| PrecisionMemBench adapter / upstream | `9b3e7cb5c964295714a561f2c86f3c4be75c7cc7` / `61a712a1754e7d27b6dee42da32a2c214b003ece` |
| Free profile | Fresh HTTP ingestion; offline BGE-small-en-v1.5,384d; enrichment/JIT/consolidation off |
| Services | Isolated per-arm stores; FalkorDB v4.18.10, Qdrant v1.11.3; pinned API image digest in manifest |
| Repair mode | Disposable fixtures deliberately stripped of vector lifecycle fields; forced reembedding |
| Enrichment mode | Deterministic extraction callback interleaving real HTTP PATCH; real graph/vector persistence |

Official paid-run metadata belongs in [AutoMem's baseline record](https://github.com/verygoodplugins/automem/pull/272). Per-fixture paired verdicts are committed in [paired-verdicts.tsv](../data/results/postmerge-20261022/paired-verdicts.tsv). [ARTIFACTS.sha256](../data/results/postmerge-20261022/ARTIFACTS.sha256) identifies the retained local raw evidence and exact launch scripts. Raw model/server payloads remain local under the repository's artifact policy.

The adapters are the existing implementations in PRs [#60](https://github.com/verygoodplugins/automem-evals/pull/60) and [#66](https://github.com/verygoodplugins/automem-evals/pull/66), pinned independently of their merge status. The ForgetEval shim changes only its imported historical server-revision constant to the arm SHA, retaining clean-source verification. PMB preparation preserves the original fixtures/scorer and its existing await-only ordering patch; it measures AutoMem through that wrapper. No upstream assertion was relaxed.

The generated dashboard reads historical raw artifacts/scores from the main checkout and overlays this branch's new report. Reproduce with `python3 data/results/postmerge-20261022/refresh_dashboard.py --data-root /path/to/automem-evals`. This calls the existing index generator and records the overlay path; it does not relabel historical scores as new runs.

## Free paired results

| Suite | Control | Candidate | Fixed | Still failing | Newly failing |
| --- | ---: | ---: | ---: | ---: | ---: |
| ForgetEval | 234/385 | 234/385 | 0 | 151 | 0 |
| PMB single retrieval | 11/77 | 11/77 | 0 | 66 | 0 |
| PMB session retrieval | 0/12 | 0/12 | 0 | 12 | 0 |
| Graph full response, cold | 5/10 | 5/10 | 0 | 5 | 0 |
| Graph full response, separately enabled local JIT | 5/10 | 5/10 | 0 | 5 | 0 |
| Exact/hierarchical tag fixtures | 20/22 | 22/22 | 2 | 0 | 0 |

Zero ForgetEval adapter errors and zero PMB protocol errors. PMB assertion processes exit1 because assertions fail; both bridges exit0 and all89 records are present. Those failures are baseline observations. All unchanged failing case IDs and verdict-stable retrieval changes are in the paired TSV. There are no new failure IDs to explain.

ForgetEval categories are unchanged: substring26/36, prefix23/39, paraphrase30/38, negation38/40, temporal37/37, shared39/40, compound0/40, obfuscated identifiers4/38, cross-lingual identifiers1/38 and recursive36/39. Mutation-target selection is adapter policy, so these scores do not isolate server capability. Compound and identifier gaps remain hypotheses for later controlled experiments.

| PMB scope / arm | Mean precision | Mean recall | Mean drift | Latency mean / p50 / p95, ms |
| --- | ---: | ---: | ---: | --- |
| Single / control | 0.0738 | 1.0 | — | 41.88 /39.94 /73.16 |
| Single / candidate | 0.0801 | 1.0 | — | 32.25 /29.86 /65.36 |
| Session / control | 0.0780 | 1.0 | 0.9220 | 47.50 /43.44 /62.04 |
| Session / candidate | 0.0858 | 1.0 | 0.9142 | 66.35 /57.43 /97.18 |

Perfect expected-hit coverage coexists with heavy noise. Precision/rank changes did not cross assertion thresholds. These are one run per arm, local wrapper retrieval timings including multiple scope calls; they support no latency improvement claim or significance estimate. ForgetEval has suite wall time only.

## Correctness changes and remaining defects

| Fixture / behavior | Control | Candidate | Classification |
| --- | --- | --- | --- |
| Fresh expired and future records, current-only recall after asynchronous indexing drains | Both exposed | Both suppressed | Fixed |
| Legacy vector payload missing lifecycle keys | Obsolete records exposed | Obsolete records exposed | Still failing until repair; no automatic migration |
| Forced reembedding of disposable legacy fixtures | Expired/future/archived suppression fails | All three suppressed; active fixture retained | Fixed repair path; production repair untested |
| Slash hierarchy prefix `tags=[run,project/foo]`, semantic and tag-only | Empty | Four expected hierarchy fixtures | Fixed 2/2 |
| Exact delimiter spelling and prefix segment boundaries | Pass 20/20 | Pass 20/20 | No regressions; foo excludes foobar/foo-bar |
| Concurrent caller tag/metadata PATCH during background and JIT extraction | Caller updates lost | Updates retained | Fixed 2/2 |
| Concurrent content PATCH during extraction | Stale entity tag committed | Background conflict/JIT skip; caller content retained | Fixed 2/2 at this boundary |
| Timestamp PATCH during background extraction | Old plan commits | Conflict rejects old plan | Fixed; both retain caller timestamp |
| Timestamp PATCH during lightweight JIT | Caller timestamp retained | Caller timestamp retained | Still correct; no temporal-link planning in this path |
| Replacement stored before invalidation interruption | Both OldCo and NewCo recalled | Same | Still failing partial supersede workflow |
| Invalidation completed before provenance-edge interruption | Only NewCo recalled; edge absent | Same | Recall safe at that boundary, incomplete provenance |
| Superseded source via inline relations | Leaks in 5/5 supersede fixtures | Same | Still failing full response contract |

The graph test passes top-k 10/10 and all 5 purge fixtures on both revisions, while the **full response** fails `supersede-0` through `supersede-4`. Maya's obsolete employer survives in neighbor relation content despite its absence from top-level results. This reproduces cold and with local JIT; entity seeds are verified 10/10. Filtering only top-level hits misses this defect. The interrupted supersede probes exercise the existing three-call adapter, not a native atomic API.

The candidate's retry worker also passes 5/5 focused scenarios: normal/forced transient recovery on attempt 2, permanent failure bounded to 3 attempts, configured single attempt, and competing enqueue unable to reset the attempt counter. Real Queue/Lock and frozen worker code are used; extraction and sleep are stubbed. This verifies scheduling and bounds, not live provider error parsing, actual backoff duration or daemon recovery.

The enrichment interleavings call production enrichment functions with deterministic extraction and real persistence. They establish caller-field preservation and stale-plan rejection before graph commit. They do **not** cover the later graph-to-vector race in [AutoMem#270](https://github.com/verygoodplugins/automem/issues/270): PATCH after the graph CAS can still receive obsolete derived Qdrant metadata. Keep that issue explicitly open.

## Paid stages and spend

| Stage | Completed / intended | Accuracy / per-category / retrieval coverage |
| --- | ---: | --- |
| Control stratified LongMemEval canary | 0/30 | Unmeasured |
| Candidate stratified LongMemEval canary | 0/30 | Unmeasured |
| Candidate LongMemEval-S | 0/500 | Unmeasured |
| Candidate LoCoMo including judged category5 | 0/1986 | Unmeasured |

The intended profile is fresh Voyage-4/1024d ingestion, canonical LongMemEval `baseline`, answerer `gpt-5-mini`, judge `gpt-5.4-mini-2026-03-17`, cold background/JIT/consolidation disabled and `PYTHONHASHSEED=0`. The30-question sample is the canonical first5 items per type in dataset order, identical across arms; IDs and dataset SHA-256 hashes are in the official manifest. LoCoMo retains its canonical retrieval/extraction scoring with LLM extraction disabled, auxiliary `text-embedding-3-small` similarity and category 5 judging; the `gpt-5-mini` answerer applies to LongMemEval. The launch wrapper only redirects metered provider traffic and waits for asynchronous indexing to drain; its live ingestion path remains unvalidated because preflight stopped execution.

Three preflight reservations of $0.00056325 total **$0.00168975** retained liability against the **$20** ceiling. Actual billed usage is unavailable. The first failure predates sanitized diagnostics; the next two report upstream HTTP 429, including the canonical home-config credential. Both configured OpenAI credentials pass the read-only model metadata check. The error code is unrecognized, so quota exhaustion versus a model/project rate limit is inconclusive. No judge, embedding, answer or benchmark-question calls followed these preflights.

All three ledgers remain halted. Each rollover reduced the next cap by every earlier liability; independent review verified the arithmetic and single-proxy condition. Remaining authorization is **$19.99831025**. A resume must preserve these charges, reverify prices, restore provider capacity, create at most one active proxy with a cap no higher than that remainder, and pass answerer/judge/embedding preflights before the paired canaries. The guard implementation and 31 fake-provider tests are [PR#71](https://github.com/verygoodplugins/automem-evals/pull/71).

LongMemEval overall accuracy is total correct/500; task-averaged accuracy is the arithmetic mean of the six per-type accuracies. Both remain null until the required dataset is complete and infrastructure is healthy. The full run must report both, plus all six counts. Partial files, failed runs and missing judge categories cannot become headline scores. Existing May/June and PR#266 results keep their original configurations; none is restamped as this baseline. PR#266's existing controlled replay remains evidence for its original tag-filter change.

## One next product change

1. **Now, evaluation batch:** retain this free baseline; finish the paid canaries/full runs when OpenAI capacity is restored, within the remaining cap. Freeze new product experiments until reconciliation.
2. **Next, selected product fix:** suppress invalid, archived, future and superseded memory content throughout inline relation payloads, with an explicit history opt-in if the API contract supports it. Start with `supersede-0..4` and the complete response envelope. Verify active neighbors still appear and purge/provenance behavior remains correct. Require a matched before/after against this baseline; do not broaden into lifecycle architecture.
3. **Then:** one controlled precision experiment holding corpus, embeddings, limit and scopes fixed; report recall and returned noise together. Follow with matched graph-on/graph-off evaluation measuring the complete response and answer quality.
4. **Parked:** new benchmark adapters, AMB refresh, BEAM scaling sweep, maturation, derived-state architecture and leaderboard expansion. Track#270 separately without starting a second simultaneous product change.

Candidate verification: 830 unit tests passed,1 skipped,72 deselected; MCP bridge 46 passed/5 skipped; existing eval runner suite 233 passed/13 skipped. These checks support engineering correctness. They supply no missing answer-quality score. Production stores, migrations and repairs were outside this isolated batch.
