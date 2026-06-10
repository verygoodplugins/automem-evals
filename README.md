# AutoMem Evals

`automem-evals` is the exploratory evaluation lab for AutoMem.

Use this repo for high-churn benchmark work such as ruleset experiments, seeded corpora, scenario authoring, cross-agent comparisons, and timestamped result artifacts. Use the main `automem` repo for official benchmark harnesses, published baselines, and any benchmark numbers referenced in docs, CI, or release notes.

## Repo Boundary

This repo owns:
- scenario definitions under `scenarios/`
- ruleset definitions under `rulesets/`
- seed corpora and manifests under `data/seed_memories/`
- experiment runners under `runners/` and helper scripts under `scripts/`
- exploratory summaries and per-run comparison artifacts under `data/results/`

This repo does **not** own:
- official LoCoMo / LongMemEval benchmark claims
- release-gating benchmark flows
- canonical published baselines for AutoMem

Those stay in `automem`. See [`docs/REPO_BOUNDARY.md`](docs/REPO_BOUNDARY.md) here for the working contract between repos.

## What Exists Today

The current implementation is a focused recall-quality harness against a locally running AutoMem stack.

- Compare multiple recall parameter rulesets against the same scenario set
- Seed synthetic corpora into AutoMem with stable scenario-to-memory mappings
- Generate timestamped markdown reports for quick A/B analysis
- Prototype retrieval behavior such as client-side graph expansion without changing `automem`

It is intentionally narrower than a full benchmark platform. Today it is primarily about answering:

> Does this recall strategy surface the right memories from a seeded corpus?

## Current Layout

```text
automem-evals/
├── rulesets/            # JSON rulesets for phase 1/2/3 recall behavior
├── scenarios/           # JSON scenarios with expected hit tags
├── runners/             # Comparison runners and experimental clients
├── scripts/             # Corpus generation, seeding, snapshotting helpers
├── data/
│   ├── seed_memories/   # Raw corpora, embedded snapshots, manifests
│   └── results/         # Summaries and timestamped comparison reports
└── docs/                # Session notes and repo-boundary documentation
```

## Quick Start

Everything here treats `automem` as a black-box server under test.

This assumes you have the sibling [automem](https://github.com/verygoodplugins/automem) repo cloned next to `automem-evals/`. Adjust paths if your layout differs.

```bash
# 1. Start AutoMem from the sibling repo
cd ../automem
docker compose up -d

# 2. Come back here
cd ../automem-evals

# 3. Seed a snapshotted corpus (v1 ships with this repo — zero API cost)
python3 scripts/seed_from_snapshot.py
python3 scripts/seed_associations.py

# 4. Compare rulesets
python3 runners/compare_rulesets.py --rulesets baseline_v1 bare_tag_1m_v2
```

Defaults assume:
- endpoint: `http://localhost:8001`
- token: `test-token`

If the AutoMem volumes were reset, reseed before scoring so the manifest matches the memory IDs currently in the server.

## Real-Data Metadata Evals In Worktrees

For production-snapshot experiments, give each `automem-evals` worktree unique
Compose project names and host ports. Keep snapshots outside eval worktrees and
pass them by absolute path. Transform-based variants can use one canonical
AutoMem checkout; server-code variants can point baseline and candidate at
different AutoMem checkouts.

Create a per-worktree env file such as `.env.metadata-<worktree>`. Files matching
`.env.*` are ignored by git. To share embedding-provider config with both stacks,
set `AUTOMEM_RUNTIME_ENV_FILE` to an AutoMem `.env` file (the eval script only loads
an allowlist of embedding-related keys).

```bash
export AUTOMEM_DIR=/path/to/automem
export AUTOMEM_PYTHON="$AUTOMEM_DIR/.venv/bin/python"
export BASELINE_AUTOMEM_DIR="$AUTOMEM_DIR"
export BASELINE_AUTOMEM_PYTHON="$AUTOMEM_PYTHON"
export CANDIDATE_AUTOMEM_DIR=/path/to/automem-metadata-sidecar
export CANDIDATE_AUTOMEM_PYTHON="$CANDIDATE_AUTOMEM_DIR/.venv/bin/python"
export LOCAL_AUTOMEM_API_TOKEN=test-token

export BASELINE_COMPOSE_PROJECT=automem_metadata_<worktree>_baseline
export CANDIDATE_COMPOSE_PROJECT=automem_metadata_<worktree>_candidate

export BASELINE_API_PORT=8111
export BASELINE_QDRANT_PORT=6443
export BASELINE_QDRANT_GRPC_PORT=6445
export BASELINE_FALKOR_PORT=6489
export BASELINE_FALKOR_UI_PORT=3110

export CANDIDATE_API_PORT=8112
export CANDIDATE_QDRANT_PORT=6444
export CANDIDATE_QDRANT_GRPC_PORT=6446
export CANDIDATE_FALKOR_PORT=6490
export CANDIDATE_FALKOR_UI_PORT=3111
```

For `metadata-embedding` or `combined`, use the same embedding family and
dimension as the restored production corpus:

```bash
export EMBEDDING_PROVIDER=voyage
export VOYAGE_API_KEY=...
export VOYAGE_MODEL=voyage-4
export VECTOR_SIZE=1024
```

Run from the eval worktree:

```bash
cd /path/to/automem-evals-worktree
set -a; source .env.metadata-<worktree>; set +a
export SNAPSHOT=/path/to/automem/lab/snapshots/<name>/snapshot.tar.gz

# Offline smoke test.
bash scripts/real_data_metadata_eval.sh --snapshot "$SNAPSHOT" --variant metadata-tags --write-probes-only

# Check the worktree-specific restore commands without touching Docker.
bash scripts/real_data_metadata_eval.sh --snapshot "$SNAPSHOT" --variant metadata-tags --restore-plan-only

# Full transform-based A/B run.
bash scripts/real_data_metadata_eval.sh --snapshot "$SNAPSHOT" --variant metadata-tags

# Full server-code A/B run. This skips corpus transforms and verifies vector identity.
bash scripts/real_data_metadata_eval.sh --snapshot "$SNAPSHOT" --variant server-metadata-search
```

Use `--skip-restore` only to rerun reports against the same already-restored
baseline/candidate stacks. Do not use it when switching variants, because the
candidate stack may already be transformed.

Operational checks:

```bash
docker ps --filter name=automem_metadata_<worktree>
curl -H "X-Api-Key: $LOCAL_AUTOMEM_API_TOKEN" "http://localhost:$BASELINE_API_PORT/health"
curl -H "X-Api-Key: $LOCAL_AUTOMEM_API_TOKEN" "http://localhost:$CANDIDATE_API_PORT/health"

cd "$BASELINE_AUTOMEM_DIR"
docker compose -p "$BASELINE_COMPOSE_PROJECT" down -v
cd "$CANDIDATE_AUTOMEM_DIR"
docker compose -p "$CANDIDATE_COMPOSE_PROJECT" down -v
```

## Experimental: BEAM via shim

`runners/run_beam.py` drives mem0's upstream BEAM runner (vendored at
`third_party/memory-benchmarks/`) against the local AutoMem stack through
`runners/beam_shim.py`, which translates mem0-OSS REST calls to AutoMem REST.
Results land under `data/results/beam/<ts>-<tier>-<convs>/` and are explicitly
**not** benchmark claims — see `data/results/beam/README.md` for the V1 shim
caveat and the promotion path.

```bash
# One-time: pull submodule + install upstream deps (PEP 668 — use a venv)
git submodule update --init
python3 -m venv .venv-beam
.venv-beam/bin/pip install -r third_party/memory-benchmarks/requirements.txt 'datasets>=2.14'

# Smoke the shim standalone (no OpenAI calls, no upstream runner)
python3 scripts/beam_shim_smoke.py --self-spawn

# Smallest end-to-end run (needs OPENAI_API_KEY; ~$2 OpenAI at 100K/2-conv)
OPENAI_API_KEY=... python3 runners/run_beam.py --tier 100K --conversations 0-1
```

## Working Rules

- Treat AutoMem as the system under test, not as a shared workspace.
- Keep official benchmark claims in `automem`, even if the exploratory work happened here first.
- If an experiment needs LoCoMo or LongMemEval, call the official harness in `automem` or label the adapter as experimental.
- Prefer curated `SUMMARY-*.md` writeups for durable findings and keep raw timestamped artifacts lightweight.

## Related

- [automem](https://github.com/verygoodplugins/automem) - backend memory service and canonical benchmark source of truth
- [mcp-automem](https://github.com/verygoodplugins/mcp-automem) - MCP server for AutoMem

## License

MIT
