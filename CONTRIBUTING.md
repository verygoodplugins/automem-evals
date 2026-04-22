# Contributing to `automem-evals`

Thanks for looking. Two things to know before you open a PR:

1. **This is a research lab, not a product.** Official benchmark claims — LoCoMo, LongMemEval, any numbers referenced in docs or release notes — live in [verygoodplugins/automem](https://github.com/verygoodplugins/automem). Do not PR new "official" benchmark results here. Exploratory findings, new scenarios, new rulesets, and failure-mode analysis are very welcome.
2. **The contract is in [`docs/REPO_BOUNDARY.md`](docs/REPO_BOUNDARY.md).** Read it before proposing anything that changes what this repo owns.

## Local setup

This repo expects the sibling [AutoMem](https://github.com/verygoodplugins/automem) repo to be cloned alongside it:

```text
OpenAI/ (or wherever)
├── automem/           # the service under test
└── automem-evals/     # this repo
```

Then:

```bash
cd ../automem && docker compose up -d
cd ../automem-evals
python3 scripts/seed_from_snapshot.py    # uses the committed v1 snapshot; no API calls
python3 scripts/seed_associations.py
python3 runners/compare_rulesets.py --rulesets baseline_v1 bare_tag_1m_v2
```

If `seed_from_snapshot.py` fails, the AutoMem stack isn't running or the volumes were just reset. See the `README.md` troubleshooting notes.

## What to keep in mind

- **Stdlib-only Python 3.10+.** There is no `requirements.txt` and no venv needed. New scripts should preserve this; if you genuinely need a third-party dep, open an issue first so we can discuss whether it belongs here or in a sibling repo.
- **No CI yet.** `python3 -m py_compile` on your changed files is the floor; running the smoke `compare_rulesets.py` invocation above is the ceiling.
- **Memory-tag convention for memories you seed:** bare tags, no namespace prefixes. Project slug for tagging memories about this repo itself is `automem-evals`. The global convention lives in `~/.claude/CLAUDE.md` and the project's `CLAUDE.md` — if you want the full picture on why tags are a hard gate on `/recall`, start there.
- **Scenario ID prefixes are conventional:** `TP-*` tensor-pipeline, `DA-*` dashboard-app, `PS-*` payment-service, `SE-*` search-engine, `OS-*` old-service, `DEBUG-*` phase-3, `SS-*` session-start, `PREF-*` preference. Keep the prefixes when adding memories or scenarios so the manifest stays scannable.
- **Timestamped artifacts under `data/results/` are not curated history.** Summaries (`SUMMARY-*.md`) are. If you want your finding to survive review, write a SUMMARY entry.

## Opening a PR

Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`. One logical change per PR. If you're adding a scenario or ruleset, include a short `docs/session_*.md` note with what you tried and what you found — that's the primary way findings propagate in this repo.
