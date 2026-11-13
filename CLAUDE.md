# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`automem-evals` is a **recall-quality evaluation harness** for the [AutoMem](https://github.com/verygoodplugins/automem) server. It is NOT a general eval framework — every runner, scenario, and metric is shaped around the `/recall` HTTP endpoint of a locally running AutoMem stack.

The end goal is answering "does this ruleset (the set of `recall_memory` parameters an agent is instructed to use) surface the right memories?" by running the **same scenarios** across different **rulesets** against a **seeded corpus** with known ground-truth hits.

Official benchmark claims do **not** live here. `automem` remains the source of truth for official LoCoMo / LongMemEval harnesses, published baselines, and any benchmark numbers referenced in docs, CI, or release notes.

See `docs/REPO_BOUNDARY.md` for the repo split.

## Architecture — the three moving pieces

```
ruleset (JSON)  ──►  runner (Python)  ──►  corpus+manifest (JSONL/JSON)
     │                    │                         ▲
     │                    └──── HTTP /recall ───────┘
     ▼                           (localhost:8001)
  recall params                                     │
  (phase 1/2/3)                                     ▼
                                         scenario → expected memory_ids
                                         expected_hit_tags (in scenario)
                                         map through manifest["scenario_to_memories"]
```

### Rulesets (`rulesets/*.json`)
Each file defines **phase_1_preferences / phase_2_task_context / phase_3_debugging** parameter dicts. These mirror the two-phase recall convention documented in the global `~/.claude/CLAUDE.md`. Comparing rulesets IS the primary experiment — `iso_a`..`iso_j` isolate individual knobs (limit, time_query, auto_decompose, tag gate, expand_relations) to attribute gains to specific changes.

The `bare_tag_1m_v2` ruleset represents the currently-recommended defaults (90-day window, limit 20/30, auto_decompose). `baseline_v1` represents the pre-v2 template for A/B comparison.

### Scenarios (`scenarios/*.json`)
A scenario is `{id, phase, query?, project_slug?, expected_hit_tags}`. **Scoring is indirect**: `expected_hit_tags` are NOT memory tags — they are scenario IDs (e.g. `TP-AUTH`, `DEBUG-CI`) that the manifest resolves to memory_ids via `scenario_to_memories`. A memory can hit multiple scenarios by listing them in `metadata.hits_scenarios` at seed time.

### Corpus + manifest (`data/seed_memories/`)
- `corpus_v1.jsonl` (78 memories, hand-authored) and `corpus_v2.jsonl` (370 memories, parameterized generator) are the raw seed.
- `*.embedded.jsonl` is the same plus pre-computed Voyage `voyage-4` 1024d vectors, produced by `snapshot_corpus.py` after a slow first seed. **Reseeding from the embedded snapshot is the fast, $0 path.**
- `*.manifest.json` holds the bidirectional mapping (`memory_to_scenarios` / `scenario_to_memories`) required by scoring. It is produced at seed time and must match the memory_ids currently in the server.

## Commands

Everything assumes Python 3.10+ (scripts use `dict | None`). **Stdlib only — no `requirements.txt`, no venv needed.**

```bash
# 0. Start the AutoMem stack (sibling repo, required — assumed to be at ../automem)
cd ../automem && docker compose up -d

# Verify: http://localhost:8001/health reports falkordb + qdrant up

# 1a. Fast reseed (v1, uses snapshotted embeddings, no API calls).
#     Timestamps are rebased to today by default (see invariant 7).
python3 scripts/seed_from_snapshot.py
python3 scripts/seed_associations.py     # adds typed edges for expansion experiments

# 1b. v2 reseed. From the embedded snapshot it is $0 (writes corpus_v2.manifest.json):
python3 scripts/seed_from_snapshot.py --snapshot corpus_v2.embedded.jsonl
#     Without a snapshot, seed raw (server embeds), then snapshot for next time:
python3 scripts/seed_corpus.py --corpus corpus_v2.jsonl
python3 scripts/snapshot_corpus.py --corpus corpus_v2

# 1c. Isolated stack (never reuse the default manifest names for a throwaway stack;
#     they would point the default :8001 runs at the wrong memory_ids)
python3 scripts/matrix_stack.py up --label candidate --api-port 8011
python3 scripts/seed_from_snapshot.py --endpoint http://localhost:8011 \
    --manifest-output corpus_v1-8011.manifest.json
python3 scripts/seed_associations.py --endpoint http://localhost:8011 \
    --manifest corpus_v1-8011.manifest.json

# 2. Run a ruleset comparison (writes data/results/<timestamp>-comparison.md)
python3 runners/compare_rulesets.py --rulesets baseline_v1 bare_tag_1m_v2
python3 runners/compare_rulesets.py \
    --rulesets baseline_v1 bare_tag_1m_v2 \
    --scenarios session_start_v2 --manifest corpus_v2.manifest.json

# 3. Knob-isolation sweep (attributes v2's gain to individual parameters)
python3 runners/compare_rulesets.py --rulesets \
    iso_a_baseline_all_off iso_b_bump_limit iso_c_bump_time iso_d_add_decompose \
    iso_e_drop_tag_gate iso_f_add_expand iso_g_all_new_v2 \
    iso_h_v2_no_gate iso_i_v2_no_gate_expand iso_j_v2_expand

# 4. Client-side graph expansion prototype (--endpoint/--token/--manifest as above)
python3 runners/client_side_expand.py --ruleset bare_tag_1m_v2 --scenarios graph_expansion_v1

# Tests (stdlib unittest)
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s runners -p 'test_*.py'
```

**Endpoint + token defaults:** `http://localhost:8001` and `test-token`. Override with `--endpoint` / `--token`. There is no production endpoint; this repo is local-only.

**If you reset the AutoMem volumes** (`docker compose down -v`), the manifest becomes stale and scoring collapses to all-zero — always re-run `seed_from_snapshot.py` (which rewrites the manifest) after a volume reset.

## Running a single scenario

There is no built-in `--scenario-id` filter. Either:
- Edit the scenarios file to remove everything but the target entry, or
- Construct the `/recall` call by hand: `runners/compare_rulesets.py:run_phase` shows the exact parameter-construction logic per phase.

## Critical invariants (non-obvious)

1. **Tags are a hard gate on `/recall`.** A memory without a matching tag is excluded before scoring even if it is a perfect semantic match. This is why `scenarios[].project_slug` + `ruleset.tags_from: "project_slug"` is the dominant knob.
2. **Server-side `expand_relations` is a no-op under tag gating** — the server filters expansion targets by the same tag filter. `runners/client_side_expand.py` exists because of this; it walks inline `results[].relations[]` to approximate an ungated expansion pass. When experimenting with expansion, prefer the client-side runner over adding `expand_relations: true` to a ruleset.
3. **Phase 1 uses tag-only, no query.** Phase 2 uses semantic + project-gated + time-windowed. Phase 3 uses semantic + bugfix/solution tags. These shapes are baked into `runners/compare_rulesets.py:run_phase` — if you add a new ruleset knob, also wire it through there.
4. **Scenario IDs are conventional, not enforced.** `TP-*` = tensor-pipeline, `DA-*` = dashboard-app, `PS-*` = payment-service, `SE-*` = search-engine, `OS-*` = old-service, `VID-*` = video, `DEBUG-*` = phase-3, `SS-*` = session-start scenario (in `scenarios/session_start_*.json`), `PREF-*` = preference scope. Keep the prefix convention when adding memories/scenarios so the manifest stays readable.
5. **The `video` slug is deliberately collision-prone** in v2. Do not "fix" it by renaming — its purpose is to exercise the slug-collision case.
6. **Memories live in AutoMem, not in this repo.** Do not treat the JSONL as source of truth for what the server returns — server-side enrichment (summary, entity extraction) mutates fields after ingest. For debugging recall, always inspect `/memory/<id>` or `/recall` response, not the seed file.
7. **Seed timestamps are rebased to today by default.** The generators bake a fixed `NOW` (v1 2026-04-17, v2 2026-04-18) and phase-2 rulesets filter by `time_query` against the server clock, so unshifted corpora age out of every window (from mid-July 2026 every phase-2 `/recall` returned 0). `seed_from_snapshot.py` and `seed_corpus.py` shift `timestamp` / `t_valid` / `t_invalid` forward by whole days (`scripts/seed_rebase.py`) so the generator `NOW` lands on today without any record becoming future-dated. `--no-rebase` seeds stored dates; `--rebase-anchor` picks the instant that becomes today. Dates written inside `content` are not shifted. If you change a generator's `NOW`, update `KNOWN_ANCHORS` (a test checks they match).

## Session notes & results

- `docs/experiments/STATUS.md` — generated experiment dashboard; start here when orienting across hypotheses, results, decisions, active worktrees, and undocumented run artifacts. Update `docs/experiments/registry.json`, then run `python3 scripts/experiment_index.py` before ending a substantial experiment session.
- `docs/session_*.md` — dated narrative notes per session; read these for context when revisiting an old result.
- `data/results/SUMMARY-*.md` — headline writeups per major experiment.
- `data/results/<timestamp>-comparison.md` — raw per-run report produced by `compare_rulesets.py`. These accumulate; the SUMMARY files are the curated view.

## Memory rules (from global `~/.claude/CLAUDE.md`)

The global file is authoritative. Two project-specific notes:

- **Project slug for AutoMem memory tags is `automem-evals`** (bare, no `project/` prefix).
- **Do not store memories about transient per-run findings** (specific hit counts for a ruleset on a given day). Do store design decisions, surprising non-obvious behaviors of the AutoMem server exposed by evals, and rule-of-thumb conclusions that survive re-runs.
