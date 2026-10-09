# Veracium feasibility verification — 2026-10-09

Outcome: **not_scored**. No AutoMem ingestion, answerer/judge call, adapter,
synthetic replacement, score, or companion product change was made.
Tracking: [issue #62](https://github.com/verygoodplugins/automem-evals/issues/62).

## Source checkout and exact commands

Run from the isolated automem-evals worktree:

```sh
git clone --depth 1 https://github.com/veracium-ai/Veracium.git .agent-drafts/Veracium
git -C .agent-drafts/Veracium rev-parse HEAD
python3 -m venv .agent-drafts/venv
UV_CACHE_DIR="$PWD/.agent-drafts/uv-cache" uv pip install --python .agent-drafts/venv/bin/python pydantic pytest
shasum -a 256 .agent-drafts/Veracium/tests/eval/scenarios.json
```

Captured source revision: `f7a1a42159b1027b75e8a0c08e7cc4874b92e1b2`.
For later reproduction, pin that revision before installing or running:

```sh
git -C .agent-drafts/Veracium fetch origin f7a1a42159b1027b75e8a0c08e7cc4874b92e1b2
git -C .agent-drafts/Veracium checkout --detach f7a1a42159b1027b75e8a0c08e7cc4874b92e1b2
```

The commands above record the original checkout; this explicit checkout pins
subsequent reproductions. MIT library v0.26.1; Python 3.14.7, SQLite 3.53.4,
pydantic 2.14.0, pytest 9.1.1. Acceptance fixture SHA-256:
`676375e68d5dbfcd0471a22e1002930762d0e72391928562430b7f29951c3f08`.

Import/schema feasibility check (exit 0):

```sh
.agent-drafts/venv/bin/python -c 'import sys; sys.path[:0]=[".agent-drafts/Veracium/src", ".agent-drafts/Veracium"]; import tests.eval.run_eval as r; import json; x=json.loads(r.SCENARIOS.read_text()); r.check_probes(x); print("acceptance harness import and check_probes: PASS",len(x),"scenarios",sum(len(s["probes"]) for s in x),"probes")'
```

```text
acceptance harness import and check_probes: PASS 4 scenarios 5 probes
```

Acceptance runtime check (exit 1; provider forbids model calls):

```sh
.agent-drafts/venv/bin/python - <<'PY'
import sys
sys.path[:0] = ['.agent-drafts/Veracium/src', '.agent-drafts/Veracium']
from tests.eval.run_eval import run
class NoCalls:
    _models = {'judge': 'claude-haiku-5-5'}
    _max_tokens = 1024
    def __call__(self, *args, **kwargs):
        raise AssertionError('No LLM calls permitted in runtime feasibility check')
run(NoCalls(), verbose=False)
PY
```

```text
StoreVersionError: unsupported-sqlite (found=None, this build=15)
sqlite 3.53.4 is not a qualified runtime build identity; regenerate the evidence there (schema_evidence.py --runtime --write)
```

This fails while creating the first `supersession` store, before ingestion or
model invocation. No fake provider verdicts were used. The original full
traceback is retained locally in `.agent-drafts/harness-check.txt`.

Independent upstream offline gate (exit 1):

```sh
PYTHONPATH=.agent-drafts/Veracium/src .agent-drafts/venv/bin/python -m pytest .agent-drafts/Veracium/tests/eval/test_semantic_recall_gate.py -q --tb=short --basetemp=.agent-drafts/pytest > .agent-drafts/upstream-check.txt 2>&1
```

```text
4 failed, 1 passed in 0.30s
```

All four failed cases refuse SQLite at store creation. The passing case checks
the frozen vector artifact, not AutoMem retrieval. No runtime evidence was
regenerated and no upstream code was modified.

## Required repository verification

```text
$ python3 -m unittest discover -s runners -p 'test_*.py'
Ran 233 tests in 1.802s
OK (skipped=13)
exit 0

$ python3 -m unittest discover -s scripts -p 'test_*.py'
Ran 30 tests in 0.434s
OK
exit 0
```

Full stdout/stderr: `.agent-drafts/runners-tests.txt` and
`.agent-drafts/scripts-tests.txt`. Fixture-generated regression messages in
runner stdout do not indicate test failures; the unittest result above passes.

The experiment registry records `EXP-VERACIUM` as blocked. Generate its local
dashboard without refreshing unrelated historical worktree/score snapshots:

```sh
python3 scripts/experiment_index.py --no-vcs --no-amb --no-scoreboard --status .agent-drafts/veracium-STATUS.md --index-json .agent-drafts/veracium-index.json
```

Both local outputs were generated successfully. PR finalization also refreshed
the committed `STATUS.md`, `index.json`, and `scoreboard.html` using the existing
`experiment_index.write_outputs` renderers and the committed result snapshot,
adding `EXP-VERACIUM` and its PR/worktree state. All 15 historical threads,
16 recorded scores, and unrelated artifact/VCS snapshots were preserved. This
registry refresh does not re-run or re-score earlier experiments.

The required next slice is an
official-artifact adapter plus real smoke run after release/runtime blockers
are resolved; scored evaluation additionally requires validated model access.
PR creation and signed AutoVault babysit finalization belong to the orchestrator.
