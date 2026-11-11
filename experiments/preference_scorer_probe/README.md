# Synthetic preference scorer probe

This is a prepared **diagnostic**, not a change to benchmark scoring policy. It targets a known failure in the earlier preference calibration: accepting an answer that satisfies one part of a compound requirement while omitting another.

The fixture contains 16 fictional, manually authored cases: eight development and eight separate held-out cases. Each split covers conjunctions, missing clauses, paraphrases, optional details, contradictions, abstention and distracting partial answers. Labels are manually assigned; this is a small synthetic set, not human gold, a representative benchmark sample, or evidence that a scorer is suitable for production. No original benchmark question, saved answer, user trace or private data is copied into the fixture.

The runner sends one question, answer, required criteria and optional guidance to the locally installed `qwen3.6:35b-a3b` through an explicit loopback Ollama endpoint. It never sends the expected label, split, category or case identifier. It disables proxy environment settings, rejects non-loopback endpoints and remote-model references, and requires a full installed-model digest. No paid provider call is used.

The scorer returns one status and supporting quote per required criterion. The runner checks JSON structure, criterion coverage, verdict consistency and that each provided quote is a literal answer substring; `met` and `contradicted` require such a quote. **A literal quote is not proof that a criterion was semantically satisfied.** In particular, the runner cannot mechanically prove an `unmet` judgment or that a compound criterion was fully addressed. Error/ambiguous cases remain visible; manual review is necessary before interpreting an improvement.

## Freeze before held-out evaluation

1. Run the development split and inspect local results. Invalid structured output is a failed case, not a pass. The runner writes `frozen.json` only if every development response passes its structural checks; it does not require a passing accuracy score.
2. Before examining or running the held-out split, freeze the scorer configuration. The frozen record binds the complete fixture, held-out subset, source runner, prompt, output schema, model name/digest and generation options. The held-out run refuses any mismatch, including a different model digest or modified fixture. The held-out hash is hard-coded in the runner; changing the held-out cases requires a new version rather than reuse under the old identity.
3. Run the held-out split once under the frozen configuration. Keep development and held-out results separate. Do not revise the prompt or cases after inspecting held-out outcomes and present the same held-out set as fresh evidence; a revised scorer requires a newly authored, disjoint holdout.

The fixture is committed and thus visible to a researcher; the runner's checks do not cryptographically blind a person who chooses to inspect it. The evaluation's validity depends on following the freeze discipline above. Synthetic cases in one category share a theme and the sample is small, so report individual category counts and false passes rather than overinterpreting a percentage.

## Run when authorized

This preparation **did not run inference**. Confirm a local Ollama server is running at the loopback IP, and that its local model list contains the required model. `--output-dir` must be a new directory outside the git worktree; each run writes local per-case JSONL and a sanitized aggregate summary. Do not commit raw response files. The returned aggregate contains counts and hashes rather than questions, answers, or model responses, but review it before publication.

```sh
python3 -m unittest discover -s experiments/preference_scorer_probe -p 'test_*.py' -v
python3 experiments/preference_scorer_probe/run.py --phase development \
  --output-dir /tmp/automem-scorer-development-20261111
# After inspecting development and freezing the setup, without tuning on held-out cases:
python3 experiments/preference_scorer_probe/run.py --phase heldout \
  --freeze /tmp/automem-scorer-development-20261111/frozen.json \
  --output-dir /tmp/automem-scorer-heldout-20261111
```

The two output directories must not exist beforehand. A local Ollama connection failure, missing model/digest, changed freeze, malformed response or invalid literal quotation is reported rather than silently scored. `temperature=0` and a fixed seed improve reproducibility but do not guarantee bit-identical local inference. The summary contains elapsed time as an observation, not a performance benchmark.
