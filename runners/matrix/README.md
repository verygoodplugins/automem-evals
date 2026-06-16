# Matrix Parallel Harness

This package lives in the `automem-evals` worktree at
`/Users/jgarturo/Projects/OpenAI/automem-evals.worktrees/matrix-harness`
on branch `feat/matrix-parallel-harness`.

## Scoring primitives

Scoring is **imported, not reimplemented**. `lab_metrics` and `lab_corpus`
are loaded from the automem repo at runtime. Set the env var:

```bash
export AUTOMEM_DIR=/path/to/automem   # default: /Users/jgarturo/Projects/OpenAI/automem
```

The harness appends `$AUTOMEM_DIR/scripts/lab` to `sys.path` at import time.
Never copy or duplicate scoring functions here.

## Running the smoke test

The smoke test provisions two isolated stacks on a 10-memory synthetic
corpus, scores them, and prints the winner — no production clone needed.

```bash
AUTOMEM_DIR=/Users/jgarturo/Projects/OpenAI/automem \
  python -m runners.matrix.smoke
```

Docker must be running. Expect the two stacks to come up on ports 18001 and
18011 (derived from `cell_ports(0)` and `cell_ports(1)`). Both stacks are
torn down in a `finally` block even if scoring fails.

## Manifest and resume model

Each matrix cell is identified by a deterministic `cell_key` — a SHA-256
digest of `(config_dict, automem_commit, seed, snapshot_id)`. Results are
written to:

```
data/results/<results_dir>/<cell_key>.json
```

A cell is **done** if and only if its result JSON file exists. To force a
re-run of one cell, delete that file:

```bash
rm data/results/<run_dir>/<key>.json
```

Re-running the orchestrator will skip all cached cells and only reprovision
the ones whose result files are missing.

## Isolation rules

Config variants are **fully isolated**: each cell gets its own Docker
Compose project (`-p automem_eval_<name>`) with a generated override file
that:

- Bakes `SEARCH_WEIGHT_*`, `RECALL_*`, `CONSOLIDATION_*`, and any other
  config knobs directly into the `flask-api` `environment:` block at `up`
  time. AutoMem reads these at import, so the config is truly per-stack.
- Assigns unique host ports via `cell_ports(index)` (deterministic: api at
  `base + 0`, falkor at `base + 1`, falkor_ui at `base + 2`, qdrant at
  `base + 3`). No fixed/literal ports appear in any generated override.
- Uses no `container_name` (which would break parallel isolation).

Never pass config via a shared `.env.bench` or a mounted env file — that
leaks across stacks.

## Path to a full-corpus run

The smoke test uses a synthetic 10-memory corpus seeded inline. A
production-quality matrix run requires three additional steps, each a
separate supervised operation:

1. **Restore a production snapshot into each stack.** Replace the
   synthetic `_seed` call in `smoke.py` with
   `clone_production.sh --restore-only` (from `automem/scripts/lab/`)
   pointed at a fresh stack. This requires production backup access and
   should be done under supervision.

2. **Supply the real query set.** Replace the inline query list with the
   output of `create_test_queries.py` (also in `automem/scripts/lab/`),
   which generates queries with ground-truth `expected_ids` from the
   seeded corpus.

3. **Set a real `automem_commit` and `snapshot_id`.** Use the actual git
   SHA of the automem build under test and the snapshot identifier from
   `clone_production.sh` so results are fully reproducible and
   attributable.

> **Note:** the full-corpus run needs production backup access and is a
> separate, supervised step. Do not automate it without explicit sign-off.

## Running the unit tests

```bash
AUTOMEM_DIR=/path/to/automem \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest tests/matrix/ -v
```

All 12 tests (manifest, compose_lint, resources, override, score,
orchestrator, live_helpers) should pass without Docker.
