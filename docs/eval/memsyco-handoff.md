# MemSyco-Bench issue and PR handoff

Prepared for the orchestrator. External writes are disabled for this worker:
no issue/PR was opened, branch pushed, hosted review/CI started, or merge made.
Replace the issue link in the PR body after publishing the issue.

## Issue draft

**Title:** eval(memsyco): memory-use authority and sycophancy track

Candidate fingerprint: `opportunity:automem-graph-rag-research-scout`.
Track [MemSyco-Bench](https://arxiv.org/html/2607.01071v2) as a separate
AutoMem memory-induced sycophancy/bias-propagation diagnostic. All-state
MemSyco/sycophancy issue and PR searches returned no results on 2026-10-25.

[Author code/data](https://github.com/XMUDeepLIT/MemSyco-Bench/tree/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a)
and [leaderboard](https://xmudeeplit.github.io/MemSyco-Bench-Leaderboard/)
are public. The local smoke loads 1,550 rows and dry-plans one example per task,
but the upstream integrity suite fails Objective Fact Judgment's manifest hash.
**`not_scored`; scores/rates null.** No AutoMem answer run has occurred.

- [ ] Resolve upstream release integrity and pin attributable artifacts.
- [ ] Implement the five-role adapter in `docs/eval/memsyco.md`, preserving
  dialogue-only ingestion and keeping gold labels out of recall/generation.
- [ ] Verify `t_valid`/`t_invalid`, supersedes, old→new edges, scope, and abstention.
- [ ] Pin reader/judge settings; run a local sample per task with controls.
- [ ] Report official metrics and retrieval/use diagnostics separately, with
  cold/matured labels and exact commands; never fabricate scores.

Related distinct work: #50, #51, #62 and PRs #61/#63. Commands, sample IDs and
the integrity failure are in `docs/eval/memsyco-verification.md`.

## PR draft

**Title:** docs(eval): add MemSyco-Bench track and public-artifact preflight

Add a MemSyco-Bench status document, a five-task AutoMem adapter plan, and
reproducible public-data smoke evidence. Cover reject/constrain/update/reconcile/
leverage behavior, temporal validity, lifecycle direction, scope/provenance,
gold isolation and abstention. Register the experiment and update its dashboard.

The dataset, harness and board are public. All 1,550 rows load; four of five
manifest hashes match. The upstream dataset suite fails on Objective Fact
Judgment's checksum, independently confirmed against pinned raw GitHub bytes.
AutoMem remains **`not_scored`**, scores/rates null; the runner is planned.

Review contract: documentation/status only; preserve the public-release versus
integrity-blocked distinction, source pins, and absence of AutoMem scores.
Verification commands and captured results: see the quoted verification block
below and `docs/eval/memsyco-verification.md` for upstream smoke commands.
Related issue: pending orchestrator publication of the draft above.

```text
$ export PATH=/opt/homebrew/opt/python@3.12/libexec/bin:$PATH
$ python3 -m unittest discover -s runners -p 'test_*.py'
Ran 233 tests in 1.693s; OK (skipped=13)
$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 30 tests in 0.410s; OK
$ python3 -m unittest discover -s scripts/benchmarks -p 'test_*.py'
Ran 7 tests in 1.021s; OK
$ uv run --with pytest --with pyyaml --with requests python -m pytest tests/matrix/ -q
12 passed in 0.41s
$ python3 -m py_compile scripts/experiment_index.py
exit 0
$ git diff --check
exit 0
```

Registry/index parity and exact dashboard renderer checks pass. Chrome DOM and
screenshots verify the author board, the new parked scoreboard row, and all
five rendered scenario mappings without page errors or document overflow.
The separate upstream data suite ran 3 tests with 1 checksum failure (exit 1);
the five-task RawDialogue harness dry run exited 0. These are preflight results,
not scored AutoMem results. Historical dashboard snapshots are preserved.
