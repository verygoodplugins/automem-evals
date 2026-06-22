# Experiment Tracking

This folder is the durable map of experiment threads in `automem-evals`.

- `registry.json` is the curated source of truth. Edit this file when starting, finishing, parking, adopting, or superseding an experiment thread.
- `STATUS.md` is generated. Read it for the current high-level overview, worktree reconciliation, and undocumented run artifacts.
- `index.json` is generated machine-readable state for agents and future tools.
- `scoreboard.html` is generated. A self-contained, dependency-free page (inline data + inline SVG charts) you can open in any browser outside Cursor: `open docs/experiments/scoreboard.html`. It charts BEAM-judged accuracy across runs, per-ability breakdowns, run provenance, the AMB cross-benchmark family (accuracy + 95% CI whisker, recall latency, context tokens), and the thread ledger. **Internal only — not a published benchmark.** Public, vetted numbers live in `automem` / on the website (see `docs/REPO_BOUNDARY.md`).

## Update Flow

1. Add or update a record in `docs/experiments/registry.json`.
2. Run:

   ```bash
   python3 scripts/experiment_index.py
   ```

3. Review `docs/experiments/STATUS.md` and open `docs/experiments/scoreboard.html`.
4. If the "Undocumented Runs" section has entries, either add those artifacts to the right registry record or create a new parked stub record for later backfill.
5. Commit the registry update, generated `STATUS.md`, generated `index.json`, generated `scoreboard.html`, and any session note that explains the decision.

### Generating from a different checkout

The indexer separates *where the registry + outputs live* (`--root`, default: cwd) from *where run artifacts are scanned* (`--data-root`, default: same as `--root`). This lets you regenerate the dashboard in a worktree while reading live results from the main checkout, without touching that checkout:

```bash
# Run from the experiment-registry worktree; read real BEAM results from main
# and the AMB family from the neutral harness outputs.
python3 scripts/experiment_index.py \
  --data-root /path/to/automem-evals \
  --amb-outputs /path/to/agent-memory-benchmark/outputs
```

`--amb-outputs` points at the Agent Memory Benchmark harness's `outputs/` dir
(LoCoMo, LongMemEval, PersonaMem, BEAM tiers). It defaults to the sibling-repo
path and is **skipped silently if absent**, so generation never breaks on a
machine without that repo. The dataset run-set and accuracy/CI math mirror
`runners/amb_aggregate.py` exactly — the two must report the same numbers; if you
change one, change the other. Use `--no-amb` to omit the AMB section.

Other useful flags: `--no-scoreboard` (skip the HTML), `--no-vcs` (skip git/gh reconciliation), `--scoreboard PATH`.

## Registry Fields

Each registry record should include:

- `id`: stable experiment id, such as `EXP-BEAM-JUDGED`.
- `title`: short human-readable title.
- `status`: `in-progress`, `adopted`, `rejected`, `parked`, or `superseded`.
- `hypothesis`: what the thread was trying to prove or disprove.
- `result`: the headline finding.
- `decision`: what we decided to do with the result.
- `started` and `updated`: ISO dates.
- `artifacts`: path globs for docs, results, runners, or scripts that belong to the thread.
- `branch`, `pr`, and `worktree`: optional VCS references for reconciliation.
- `related`: other experiment ids that explain lineage.

## Session End Checklist

Before ending a substantial experiment session:

1. Write or update the relevant session note.
2. Update `registry.json` with the current status and decision.
3. Run `python3 scripts/experiment_index.py`.
4. Check that the dashboard's in-progress, worktree, and undocumented-run sections match reality.
