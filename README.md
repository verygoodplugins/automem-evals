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

Those stay in `automem`. See `docs/REPO_BOUNDARY.md` here and `automem/docs/EVALS_CONTRACT.md` in the service repo for the working contract between repos.

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

```bash
# 1. Start AutoMem from the sibling repo
cd /Users/jgarturo/Projects/OpenAI/automem
docker compose up -d

# 2. Come back here
cd /Users/jgarturo/Projects/OpenAI/automem-evals

# 3. Seed a snapshotted corpus
python3 scripts/seed_from_snapshot.py
python3 scripts/seed_associations.py

# 4. Compare rulesets
python3 runners/compare_rulesets.py --rulesets baseline_v1 bare_tag_1m_v2
```

Defaults assume:
- endpoint: `http://localhost:8001`
- token: `test-token`

If the AutoMem volumes were reset, reseed before scoring so the manifest matches the memory IDs currently in the server.

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
