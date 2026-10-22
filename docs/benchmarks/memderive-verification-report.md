# MemDerive verification report — 2026-10-22

Route: isolated `agent/kernel-worker/328d6b09` worktree; read-only GitHub CLI
searches; official archive download through Chrome; stdlib HTTP adapter to local
AutoMem and local MLX/Ollama reader. No companion repository was changed.
This is a committed implementation handoff: the orchestrator owns PR creation
and signed AutoVault finalization. No issue, push, PR, review or CI was created
by the worker. Use the plan plus this report as the PR body.

## Commands and results

| Command | Result |
| --- | --- |
| `gh issue list --repo verygoodplugins/automem-evals --state all --search MemDerive --limit 100 --json number,title,state,url` | `[]`; matching all-state `gh pr list` also `[]`. Broader searches included MemTrace, StateMemBench and A-TMA; direct reads confirmed #50/#51 open and PR #58 merged. |
| `uvx flake8 scripts/benchmarks/memderive/pilot.py scripts/benchmarks/test_memderive_pilot.py` | PASS; zero findings. |
| `uvx flake8 runners scripts` | FAIL; 1,361 existing findings, none in the two added Python files. Example: `runners/amb_aggregate.py:85:89 E501 (91 > 88 characters)`. Baseline is not lint-clean; unrelated files were not repaired. |
| `/opt/homebrew/bin/python3.12 -m unittest discover -s runners -p 'test_*.py'` | PASS; 233 tests, 13 skipped. |
| `/opt/homebrew/bin/python3.12 -m unittest discover -s scripts -p 'test_*.py'` | PASS; 30 tests. |
| `/opt/homebrew/bin/python3.12 -m unittest discover -s scripts/benchmarks -p 'test_*.py'` | PASS; 10 tests including the three new HTTP-boundary tests. |
| `uvx --with pyyaml --with requests pytest tests/matrix` | PASS; 12 tests. Initial collection without `requests` failed; the explicit dependency resolves it. |
| `/opt/homebrew/bin/python3.12 -m py_compile scripts/benchmarks/memderive/pilot.py scripts/benchmarks/test_memderive_pilot.py` | PASS. |
| `git diff --check` | PASS. |
| `/opt/homebrew/bin/python3.12 scripts/experiment_index.py --no-vcs --no-amb --no-scoreboard --index-json tmp/memderive/experiment-index.json` | PASS; registry/dashboard refreshed without review or CI finalization. |

Pilot command:

```bash
PYTHONPATH=tmp/memderive/eval/src /opt/homebrew/bin/python3.12 \
  scripts/benchmarks/memderive/pilot.py --data tmp/memderive/data \
  --output tmp/memderive/pilot-final
```

PASS: `status=completed`, `cleanup=completed`, 452 events, one root, five nodes,
five edges and 20 reader calls. The [plan](memderive-automem-plan.md) records
all score denominators and archive/model pins. `matured=not_run`.
A scoped post-cleanup `/recall` returned zero results. The committed
[`MANIFEST.json`](../../data/results/memderive-pilot/MANIFEST.json) retains
counts, predictions, model identity and raw-artifact checksums.
Raw reports, predictions, prompts, model responses, ID manifest, cleanup receipt
and traces remain under `tmp/memderive/pilot-final/`; these generated artifacts
are intentionally ignored. Root scoring uses the official deterministic scorer;
node/edge counts are smoke diagnostics rather than a full paper reproduction.

## Real web surface evidence

`browser-hand doctor` reported `tab_bootstrap_works`. Browser navigation, full
DOM snapshots and screenshot inspection confirmed that both paper-linked
repositories render their actual README and file tree after loading.
The dataset DOM exposes 245 files, `formal-set-v1.16`, the 10-world/1,503-question
suite, `benchmark/data/<world>/` and the ZIP link. Framework DOM exposes 1,948
files, DerivEval's backend SDK, v9 prompt and deterministic scoring instructions.
Shell fetches returning 403 were not treated as evidence of missing artifacts.

- Dataset UI: <https://anonymous.4open.science/r/DeriveMem-67C6/README.md>.
- Framework UI: <https://anonymous.4open.science/r/DerivEval-6799/README.md>.
- [Inspected dataset screenshot](evidence/memderive-release.png), captured
  2026-10-22T06:38:43Z; DOM receipts: `tmp/memderive/data-dom.json` and
  `tmp/memderive/eval-dom.json`.

Remaining work: full Q2 frontier/recovery execution, matched-token dev sweeps,
Q3 implicit-change maintenance, and the frozen narrative-time maturation profile.
Repository-wide lint remains an existing blocker to an all-green lint claim.
