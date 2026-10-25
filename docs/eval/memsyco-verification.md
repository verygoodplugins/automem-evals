# MemSyco-Bench verification — 2026-10-25

## Discovery

Executed before implementation; both commands returned `[]` (open and closed):

```bash
gh issue list --repo verygoodplugins/automem-evals --state all --search 'MemSyco OR sycophancy' --json number,title,url,state
gh pr list --repo verygoodplugins/automem-evals --state all --search 'MemSyco OR sycophancy' --json number,title,url,state
```

Read PRs #61/#63 and issues #50/#51/#62 for track/status conventions.
Memory MCP recall was unavailable in this worker's tool registry.

## Public-data smoke and harness dry run

Local-only preflight; no AutoMem writes, answer generation, paid judge, or scores.
Commands from repository root (Python 3.12.13 for repository checks):

```bash
git clone https://github.com/XMUDeepLIT/MemSyco-Bench.git tmp/memsyco-bench
git -C tmp/memsyco-bench checkout 3c3aa013ac5bee2f0e252fe8748644edc7f9af0a
cd tmp/memsyco-bench
python3 -m unittest discover -s dataset -p 'test_*.py'
bash scripts/run_benchmark.sh --dry-run --methods RawDialogue --limit 1
python3 - <<'PY'
import hashlib
from pathlib import Path
from dataset import load_dataset, load_manifest
for task, spec in load_manifest()['tasks'].items():
    rows = load_dataset(task)
    digest = hashlib.sha256((Path('data') / spec['file']).read_bytes()).hexdigest()
    print(task, len(rows), rows[0]['id'], digest == spec['sha256'])
PY
```

Observed loader output (`True` means file bytes match the published manifest):

```text
personalized_memory_use 300 v11_001093 True
valid_memory_selection 350 v11_000321 True
memory_evidence_conflict 300 emc_search_000001 True
contextual_scope_control 300 mso_hard_000001 True
objective_fact_judgment 300 consensus_obj_000001 False
```

Loader exit 0: 1,550 rows across five tasks; first ID per task recorded above.
Harness dry run exit 0: planned five `evaluation/run_task.py` invocations, each
with `--limit 1`, `--optimized`, and RawDialogue context; no model calls executed.
Upstream tests: **3 run, 1 failure**, exit 1 in `test_manifest_counts_and_hashes`:

```text
actual:   cd34eb4136dc9a5e2b4eff742a43de25d50bd1044455160a4b4eea0f082b81bc
manifest: c6ea7e17df9a90480115c0b7ebf8930aa36a39504acbfa1b650d2be167546f97
```

The [pinned raw Objective Fact Judgment file](https://raw.githubusercontent.com/XMUDeepLIT/MemSyco-Bench/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a/data/objective_fact_judgment.jsonl)
independently hashes to the actual value, ruling out local checkout conversion.
The [published manifest](https://github.com/XMUDeepLIT/MemSyco-Bench/blob/3c3aa013ac5bee2f0e252fe8748644edc7f9af0a/data/manifest.json)
was left unchanged. Dataset/harness are **public**, not unreleased.

```json
{"status":"not_scored","smoke_kind":"public_data_and_harness_preflight","loaded_rows":1550,"tasks":5,"manifest_matches":4,"manifest_mismatches":1,"automem_samples":0,"scores":null,"rates":null,"blocker":"Upstream objective_fact_judgment checksum mismatch; AutoMem adapter and reader/judge configuration remain planned."}
```

## Repository checks and rendered surface

System `/usr/bin/python3` is 3.9 and cannot import this repo's `datetime.UTC`; checks use
Homebrew Python 3.12 through PATH, without changing tracked configuration.

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

Ran `python3 scripts/experiment_index.py --no-vcs --no-amb` with outputs under
`tmp/`. Merged only the new thread/artifacts/worktree into the committed index
snapshot, preserving historical scores, artifacts and VCS observations; rendered
STATUS and scoreboard with existing `write_outputs`. Registry/index field parity
and exact `render_status`/`render_scoreboard_html` equality both pass. Historical
observations are not refreshed by this narrow track addition.

Headless Chrome via Playwright verified the real leaderboard DOM (title
`MemSyco-Bench Leaderboard`, one table) and captured its screenshot. The local
scoreboard renders one `EXP-MEMSYCO` row: parked, three artifacts, correct next
step. Rendered track Markdown has two tables, five scenario rows, visible
`not_scored`, no page errors, and no horizontal overflow at 1440×1000. Screenshots
and DOM evidence are local handoff artifacts under `.agent-drafts/`:
`memsyco-leaderboard.png`, `memsyco-dashboard.png`, `memsyco-document.png`, and
`render-evidence.json`. No companion repository was changed.
