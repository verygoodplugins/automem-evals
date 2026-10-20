# DolphinBench tracking verification report

Date: 2026-10-20. Scope: source verification and follow-up planning; no adapter
behavior changed and no scored AutoMem evaluation was executed.

## Tracking route

Searched all states of GitHub issues and PRs in `verygoodplugins/automem-evals`
for `DolphinBench in:title,body,comments` and
`2609.24971 in:title,body,comments`. Direct matches were closed issue #45 and
merged PR #46. Added the [acceptance follow-up to #45](https://github.com/verygoodplugins/automem-evals/issues/45#issuecomment-6285270104);
no duplicate issue, new PR, push, review/CI finalization, or merge was performed.
Only this isolated worktree changed; no companion repository changed.

## Source evidence

Paper v2 and project/dataset/run pages were available. GitHub verified commit
`81cb6f8405b40a9e76089cef650806a80af06ea2` and its recursive tree without
truncation. It contains 200 task YAMLs per persona and a root Apache-2.0
license; no other license file was found. Downloaded ten files: manifest,
license, runner, loader, three histories, and the first task for each persona.
All seven downloads covered by the pinned manifest matched its hashes.
The manifest contains 637 checksums and user-message token counts of 500100
(Morgan), 500109 (Alex), and 500056 (Riley).

Raw downloads, observed SHA-256 values and test logs are local under ignored
`tmp/dolphinbench/`; durable pins, central hashes and implementation acceptance
are in [the assessment](dolphinbench-eval.md). Remaining task bytes, shared
state, dependencies and upstream model/judge execution were not validated.

## Test evidence

The default `python3` is system Python 3.9.6. The exact requested commands
initially failed on existing compatibility requirements: runner suite 233
tests, 5 errors, 13 skips (`zip(strict=...)` and union annotations); script
suite 10 tests, 3 setup errors (`datetime.UTC` and union annotations).

With `PATH=/opt/homebrew/opt/python@3.12/libexec/bin:$PATH`, `python3` is
Python 3.12.13. Both requested commands passed:

```text
python3 -m unittest discover -s runners -p 'test_*.py'
Ran 233 tests; OK (skipped=13)
python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 30 tests; OK
python3 -m unittest scripts/benchmarks/test_dolphinbench_adapter.py
Ran 2 tests; OK
python3 scripts/benchmarks/run_dolphinbench_smoke.py
status=not_scored; accuracy=null; total_cost_usd=null; median_task_latency_s=null
git diff --check
Passed
```

The offline smoke reports the protocol boundary, not a real service/agent run.
No paid model or judge calls were made. Loopback validation, fresh-scope
enforcement, graph expansion, durable checkpoints and manifested cleanup
remain explicit follow-up requirements. No accuracy, cost or latency score is
claimed. AutoMem MCP tools were not exposed in this worker, so session memory
recalls were unavailable; repository and upstream evidence supplied context.
