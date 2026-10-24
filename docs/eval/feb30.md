# FEB-30 intrinsic evaluation — release blocked

Tracker: [#74](https://github.com/verygoodplugins/automem-evals/issues/74).

Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.

## Evidence checked 2026-10-24

[Toma et al., arXiv:2610.22209v1](https://arxiv.org/abs/2610.22209v1)
introduce 30 fact-evolution trajectories, six diagnostic categories, and three
difficulty levels. The paper reports 16 percentage points of intrinsic/extrinsic
divergence and approximately 20% operation classification accuracy for its tested
system. These are paper findings, **not AutoMem scores**.

The [linked release](https://github.com/amazon-science/feb-30-benchmark) and
GitHub repository API return 404; repository-name search returns no matches.
No commit, license, dataset schema, or executable scorer can currently be pinned.
404 establishes inaccessibility, not whether a private repository exists.
Do not reconstruct scored trajectories from paper examples or guess a loader.

Open issue/PR searches for FEB-30 and 2610.22209 found no dedicated tracker.
Reviewed #50 StateMemBench (current-state outcomes), #51 MemTrace (evidence use),
#53 MERIT (tool actions), #66 PrecisionMemBench (retrieval precision), and
#67 StreamMemBench (feedback reuse). Store-state inspection is a distinct axis.
Follow #66's pinning, isolation, raw audit, and experiment-registration conventions.

## Delivered scaffold

`scripts/benchmarks/feb30_adapter.py` provides an HTTP loopback-IP-only
`StoreInspector`: document writes and direct snapshots of every adapter-owned
memory ID, including invalidated history. No gold labels drive writes. It refuses
redirects and inherited proxies. It does not provision a stack, infer lifecycle
operations, enumerate server-created nodes, run trajectories, or score claims.
The caller must provide a fresh dedicated stack; a unique tag is insufficient.

```bash
python3 scripts/benchmarks/feb30_adapter.py --preflight \
  --output data/results/feb30/release-check-20261024/results.json
# Exit 2: blocked, not a successful benchmark smoke. Use a new path on retries.
python3 -m unittest discover -s scripts -p 'test_*.py'
```

The committed raw preflight records the API response and null scores/model fields.
**No AutoMem cold smoke ran.** Answerer and judge: none. No embedding, extraction,
or synthesis model was invoked. `requested_maturation=cold` describes intent,
not a measured run; matured evaluation is also unexecuted.

## Acceptance criteria for the runnable follow-up

- [ ] Pin official code/data commit, checksums, license, loader, and scorer.
- [ ] Provision a dedicated loopback-bound Compose project with fresh volumes;
  record AutoMem SHA/config, cold settings, readiness, and teardown. Never reset
  an existing evaluation stack. Follow `docs/eval/maturation.md` for later runs.
- [ ] Ingest official artifacts chronologically through an explicit memory-writing
  policy. Keep gold claims, operations, expected answers, and judge rationales
  outside ingestion and answer prompts. Do not turn gold actions into API writes.
- [ ] After each step, preserve write responses, complete store enumeration,
  direct node fields (`t_valid`, `t_invalid`), and lifecycle edges. Audit
  `INVALIDATED_BY`/`EVOLVED_INTO` as old → new; test current-only suppression
  separately. `/recall` top-k is not a complete intrinsic store dump.
- [ ] Preserve the official entailment matcher/judge and scoring. Report claim
  coverage per state and trajectory; update detection over update/supersede
  states; false update rate over reinforcement states. Keep empty denominators
  explicit. Appendix C allows partial entailment credit: verify executable
  scorer behavior before resolving the binary equation/graded-prompt distinction.
- [ ] Capture observed operation labels and confusion counts for create, update,
  reinforce, supersede; mark unobservable labels unavailable. Never equate a
  successful HTTP write with correct operation classification.
- [ ] Run an official small cold subset; retain raw per-step states, model outputs,
  counts, exclusions, commands, revisions, prompts/settings, latency, and errors.
  Report intrinsic results separately from extrinsic QA and paired divergence.
  Disclose answerer, entailment judge, answer judge, extraction/synthesis models,
  embedding model, and retrieval budget. The paper uses Nova Pro answers and
  Haiku 4.5 judges (temperature 0); this scaffold invokes neither.
- [ ] Register executed results and regenerate the experiment index. Keep official
  AutoMem benchmark claims in `automem`; this repository owns exploratory evals.
