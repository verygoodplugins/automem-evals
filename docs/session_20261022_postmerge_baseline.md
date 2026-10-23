# Post-merge baseline: 22 October 2026

The merged system fixes several write-path correctness defects. ForgetEval, PMB and graph suites show **no assertion regressions or pass-count gains**; targeted tag checks improve **20/22 to 22/22**. Inline superseded content still appears in recall relations, making response-envelope lifecycle filtering the next product fix. Paid LongMemEval-S completed 500/500: 427/500 (85.4%). LoCoMo completed 1986/1986 and passed native, driver-receipt and accepted-window audit gates.

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

The generated dashboard reads historical raw artifacts/scores from the main checkout and overlays this branch's new report. Reproduce with `python3 data/results/postmerge-20261022/refresh_dashboard.py --data-root /path/to/automem-evals`. This calls the existing index generator and records the overlay path. When raw AMB archives are unavailable, only three exact matching completed rows are retained from the recorded June22 index snapshot, with per-row commit/hash/date provenance and visible historical notices. Fresh, failed and unmatched rows are untouched. No historical score becomes a new baseline.

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

Both stratified LongMemEval canaries completed and passed the exact-ID, checkpoint and infrastructure gates. Each arm answered 21/30 correctly (70%). These 30-question results describe the canaries; they do not substitute for the candidate's full 500-question LongMemEval-S result or the 1,986-question LoCoMo run.

| Stage | Completion | Result |
| --- | --- | --- |
| Control stratified LongMemEval canary | 30/30; zero ingestion/judge errors | 21 correct; 70% accuracy |
| Candidate stratified LongMemEval canary | 30/30; zero ingestion/judge errors | 21 correct; 70% accuracy |
| Candidate LongMemEval-S | 500/500; zero ingestion/judge errors | 427/500; 85.4% accuracy; 83.60% task average |
| Candidate LoCoMo, including judged category 5 | 1986/1986; all five categories | 1690/1986; 85.10% accuracy |

The canary selects the canonical first five questions of each type in dataset order, with identical IDs across arms. Correct counts by type are:

| LongMemEval type | Control | Candidate |
| --- | ---: | ---: |
| Knowledge update | 2/5 | 3/5 |
| Multi-session | 3/5 | 2/5 |
| Single-session assistant | 5/5 | 5/5 |
| Single-session preference | 2/5 | 2/5 |
| Single-session user | 4/5 | 4/5 |
| Temporal reasoning | 5/5 | 5/5 |

Canary overall accuracy and the unweighted six-type average are both 70% in each arm. Full LongMemEval overall: 427/500 (85.4%); task average: 83.60% unweighted mean of six type accuracies.

| Full LongMemEval type | Correct / total | Accuracy |
| --- | ---: | ---: |
| Knowledge update | 65/78 | 83.33% |
| Multi-session | 108/133 | 81.20% |
| Single-session assistant | 55/56 | 98.21% |
| Single-session preference | 17/30 | 56.67% |
| Single-session user | 67/70 | 95.71% |
| Temporal reasoning | 115/133 | 86.47% |

Native any-support Recall@5 is 488/500 (97.6%). Full retrieved unique session IDs cover 904/948 labeled supporting sessions (95.36%); 463/500 questions retrieve all their labeled support. Of 73 wrong answers, 51 retrieve all labels, 17 retrieve some and 5 retrieve none; 68 retrieve at least one. Supporting-session precision proxy is 904/5000 (0.1808); off-label fraction is 0.8192. Supporting labels are not exhaustive relevance judgments. Wrong-answer support-miss IDs: `gpt4_f2262a51`, `d6233ab6`, `gpt4_468eb063`, `gpt4_1e4a8aec`, `gpt4_8279ba03`.

Both canaries have native any-support Recall@5 hits on 30/30 questions. Across the full retrieved unique session IDs, each covers 48/53 labeled supporting sessions (90.6%); 26/30 questions retrieve all their labeled supporting sessions. Of the nine wrong answers per arm, six have all labeled support retrieved and three have only some; none has zero labeled support. Any-support success therefore does not establish complete evidence coverage or answer correctness.

The supporting-session precision proxy is 48/300 (0.16), and the off-label fraction is 252/300 (0.84), for each arm. Supporting labels are not exhaustive relevance judgments: off-label retrieval cannot be equated with irrelevant content. These figures describe label overlap, not a measured 84% irrelevance rate.

All 30 full ranked session-ID sequences match between arms. Candidate correctness changes on two questions: `6a1eabeb` changes from wrong to correct and `0a995998` from correct to wrong. The observations are descriptive; they support no causal or statistical improvement claim. Matching retrieved IDs does not prove identical prompt bytes, which were not retained for this comparison.

The paid LongMemEval profile retains canonical `baseline`, fresh cold HTTP ingestion with Voyage-4 embeddings at 1,024 dimensions, answerer `gpt-5-mini`, pinned judge `gpt-5.4-mini-2026-03-17`, enrichment/JIT/consolidation disabled and `PYTHONHASHSEED=0`. LoCoMo retains canonical ingestion and retrieval/scoring, LLM extraction disabled, auxiliary `text-embedding-3-small` similarity and category 5 judging. LoCoMo categories and native judge status/latency:

| LoCoMo category | Correct / total | Accuracy |
| --- | ---: | ---: |
| 1 | 150/282 | 53.19% |
| 2 | 279/321 | 86.92% |
| 3 | 43/96 | 44.79% |
| 4 | 789/841 | 93.82% |
| 5 | 429/446 | 96.19% |

Native judge errors 0; skips 0; API calls 444. Judge API latency: avg 1188.128 ms, p50 1140.665 ms, p95 1589.537 ms, max 3087.315 ms.

LoCoMo supporting-session coverage and paid stale-content exposure were unmeasured.

The v2 launch instrumentation tracks every physical memory UUID even when duplicate logical session IDs overwrite entries in the canonical return map, then checks vector readiness using the frozen revision's supported signals. It preserves canonical recoverable model-JSON retries. The launch content limit is 100,000 characters so the unchanged dataset's largest 78,135-character payload can be ingested. These corrections make the frozen launch executable; they do not change server source, fixtures, question selection, prompt templates or scoring. No session was renamed, deduplicated or truncated to pass an observer gate.

Index-drain waits measure indexing readiness, not retrieval latency. The resumed control canary's native elapsed time covers only its last 20 questions. The three full-run attempt scopes are 149 + 102 + the remaining 249 questions; the final process's native elapsed time covers only those last 249, not all 500 or the earlier 351-question resume scope. Per-attempt receipts preserve the separate attempts and their abandoned work. Native timing: native 4336.94 s for final 249 only; receipt active times: 149 scored rows: 2601.73 s (incomplete attempt); 102 scored rows: 2062.18 s (incomplete attempt); 249 scored rows: 4346.19 s (complete attempt).

LoCoMo timing: native elapsed 3088.98 s for the final 1,489 rerun questions only; retained 497-row timer statistics are preserved separately, not included in that attempt elapsed. Native judge API latency as above.

Validated server-side recall processing over all 501 endpoint calls (149 + 103 + 249, including unscored question 252): n=501; mean 730.36 ms, p50 795.27 ms, p95 939.24 ms, maximum 2039.92 ms. Candidate-canary recall processing: n=30; mean 727.87 ms, p50 798.27 ms, p95 951.97 ms, maximum 993.69 ms. These are endpoint-call distributions, not 500 per-question latencies or end-to-end latency. They include query embedding/retrieval/scoring, but exclude ingestion/drain, answers/judges and client transport. Control latency is unavailable; no paired latency improvement is claimed.

[Execution provenance and receipts](../data/sweep_runs/postmerge-20261022/README.md) retain all preflights, canonical retries and abandoned work against the original **$20** cap. Full LongMemEval stopped first at 149/500 on a Voyage failure, then at 251/500 after question 252 received OpenAI HTTP 400. That same question later succeeded with unchanged prompt templates, model, data and scoring; the precise failure cause remains unresolved. Actual prompt bytes were not retained. All failed reservations remain charged; each rollover deducted earlier costs without refund or cap reset.

Final batch reconciliation: $9.809397650 accounted; $9.736267080 reconciled usage; $0.073130570 retained ambiguous/reserved; $10.190602350 remaining of the original $20. All 12 ledgers and their cap chain were checked through 2026-10-23T02:15:56.210223+00:00. This includes failed and repeated work and is not a provider billing invoice.

Official run identities, configurations and completion-gated benchmark metadata belong in [AutoMem's baseline record](https://github.com/verygoodplugins/automem/pull/272). This repository records the exploratory comparison and product decision. Partial files and failed attempts are evidence of execution and cost, not full-stage headline scores. Existing historical results retain their original dates/configurations.

A qualitative read of the saved preference answers and judge rationales found labeled support in 12 of 13 wrong preference answers. Three answers abstained, nine gave substantive answers judged insufficiently preference-specific, and one missed support. `0edc2aef` and `35a27287` illustrate abstention despite retrieved support. `0a34ad58`, `b6025781` and `1a1907b4` show partial answer/reference overlap and possible rubric sensitivity. Their recorded grades are unchanged; these examples do not establish a judge error. Full retrieved memory texts and serialized prompts were not retained, so session-ID coverage cannot prove every relevant detail reached the answerer. Distractor influence, abstention policy and answer calibration remain hypotheses, not isolated causes. Native confidence is judge confidence.

The [baseline chain-of-note prompt](https://github.com/verygoodplugins/automem/blob/3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876/tests/benchmarks/longmemeval/test_longmemeval.py#L650) asks for extraction, reasoning and abstention when information is unavailable, but does not explicitly explain how remembered preferences should guide a new recommendation. The frozen harness already offers an [answer_focus_prompt alternative](https://github.com/verygoodplugins/automem/blob/3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876/tests/benchmarks/longmemeval/test_longmemeval.py#L603) with preference-evidence guidance; that option was disabled for this baseline. This motivates a prompt-sensitivity hypothesis, not a causal explanation of these failures: actual serialized prompt bytes were not retained. Keep the answer prompt fixed in the planned precision experiment and graph comparison. Reserve a preference-evidence prompt condition for a separate later ablation after those comparisons, with one changed condition at a time and no baseline grade changes.

A Docker storage interruption stopped LoCoMo after 757 structurally bound rows. All four owned containers received coordinated SIGTERM; the actor remains unproven. The [original checkpoint and logs](../data/sweep_runs/postmerge-20261022/resume-snapshots/20261023T011445Z-locomo-failed757-quarantined/SNAPSHOT.json) were archived unchanged because successful recall responses could conceal backend errors. Recovery restored exactly 497 accepted rows from completed conversations, preserving their result bytes and timer statistics. All 260 conversation 42 rows were quarantined; the resumed run restarts that conversation from its first question. Publication requires finalized clean audits of the retained API13 window ending 2026-10-23T01:04:03.153Z and the resumed API14 receipt window, plus a successful bound driver receipt and native validation. The resumed native elapsed time covers only 1,489 rerun questions, not all 1,986; retained timers remain separate. Original and rerun costs share the same ledger and $20 cap, without refund. LoCoMo recall latency is unavailable/inconclusive; the separately validated LME 501-call distribution remains valid.

## One next product change

The baseline is complete. The first selected product change remains [automem-evals#31](https://github.com/verygoodplugins/automem-evals/issues/31): suppress obsolete source content throughout inline relation payloads. Both frozen revisions leak it in all five `supersede-0..4` fixtures. Make one bounded change, then run one matched evaluation against the retained baseline using the existing full-response scorer; preserve valid active neighbors, purge and provenance behavior.

Then run one controlled precision experiment using supported-preference cases and the five support-miss IDs above, holding corpus, embeddings, limits, scopes and the answer prompt fixed. Retain full retrieved context and serialized prompts for that experiment; evaluate rubric sensitivity without changing this baseline's grades. Follow with a matched graph-on/graph-off comparison. [AutoMem#270](https://github.com/verygoodplugins/automem/issues/270) remains OPEN as a separate graph-to-vector race. AMB refresh, BEAM scaling, new adapters, maturation and architecture work remain parked.

Candidate verification: 830 unit tests passed,1 skipped,72 deselected; MCP bridge 46 passed/5 skipped; existing eval runner suite 233 passed/13 skipped. These checks support engineering correctness. They supply no missing answer-quality score. Production stores, migrations and repairs were outside this isolated batch.
