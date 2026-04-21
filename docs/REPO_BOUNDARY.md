# Repo Boundary

`automem-evals` is the experimentation repo for AutoMem benchmark work. It exists to absorb the churn that does not belong in the product repo.

## This Repo Owns

- ruleset experimentation
- scenario authoring
- synthetic corpora and manifests
- experiment runners and helper scripts
- cross-agent and cross-backend exploratory comparisons
- timestamped result artifacts and exploratory summaries

## `automem` Owns

- official LoCoMo and LongMemEval harnesses
- published benchmark baselines
- benchmark numbers referenced in README, docs, release notes, or CI
- release-gating benchmark flows

## Contract With `automem`

- Start and manage the local stack from the `automem` repo.
- Treat the running service as a black-box server under test.
- Use the documented local surface from `automem/docs/EVALS_CONTRACT.md`.
- Do not make `automem` depend on uncommitted files from this repo.

## Avoiding Duplicate Truth

- Do not create a second "official" LoCoMo or LongMemEval benchmark here.
- If this repo needs those benchmarks, call the official harness from `automem` or keep any adapter clearly labeled as experimental.
- Promote durable findings back into `automem` only when they have been reproduced through the official benchmark flow.
