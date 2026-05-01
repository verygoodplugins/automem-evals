# Session 2026-04-28 — Layer-1 hook-replay eval harness

## Why this layer exists

The production AutoMem corpus accumulates noise from Claude Code hooks shipped by mcp-automem (~74% of recent project-tagged memories per the 2026-04-28 audit, dominated by session-summary debriefs that CLAUDE.md explicitly forbids). To validate fixes before they ship, this repo needs deterministic, zero-API-cost replay of the production hook code paths against a local Docker AutoMem.

This document records the design decisions for the **first layer** of that harness — fixture-driven hook replay. Recall probes (Layer 2) are out of scope.

## Decisions (and the alternatives rejected)

### 1. Variants are pinned by SHA, not generated synthetically
Baseline = `mcp-automem` files at `4be6724` (the SHA the audit was authored against). `fix-v1-no-session` overlays the change-of-interest (Stop hook entry removed) on top.

**Rejected:** synthesizing a hook stub from scratch. The whole point is to test the actual production code path — fakes defeat the purpose.

### 2. `eval_run_id` tag for run isolation, not docker-volume reset
Each run generates a `uuid4()` and tags every emitted memory with `eval-run-<uuid>`. Snapshot/metric queries filter on that tag. Multiple runs coexist in one corpus.

**Rejected:** `docker compose down -v` between variants. Tradeoff: faster iteration (~3s vs ~30s reset), runs are inspectable retroactively, less risk of breaking concurrent work in the AutoMem stack. Cost: corpus accumulates eval residue if `--cleanup` isn't run; mitigated by wiring `--cleanup` from day one (see decision 5).

### 3. `HOME` override for queue isolation
The runner sets `HOME=<temp_sandbox>` per fixture invocation. The hooks hard-code `MEMORY_QUEUE="$HOME/.claude/scripts/memory-queue.jsonl"` and `process-session-memory.py` uses `Path.home() / '.claude' / 'scripts' / 'memory-queue.jsonl'` — both with no env override. The runner cannot redirect via `AUTOMEM_QUEUE` env (the inline `VAR=value cmd` syntax in the hook overrides parent-shell values), so HOME-redirection is the only path that doesn't require patching the hook scripts.

The sandbox is `/tmp/eval-<uuid>/` per run; the hook will create `.claude/scripts/memory-queue.jsonl` underneath.

**Rejected:** patching the hooks at copy-time to read MEMORY_QUEUE from env. Tradeoff: defeats "test the actual production code path verbatim" — the whole point of the harness.

**Rejected:** running hooks in a Docker container. Tradeoff: ~10× more setup; HOME override achieves the same isolation more cheaply.

### 4. Stdlib-only Python, no `requirements.txt`
Mirrors `runners/compare_rulesets.py`. No venv, no install step.

**Rejected:** pulling in `httpx`, `pytest`. Tradeoff: a few more lines for HTTP boilerplate; first-run friction drops to zero.

### 5. `--cleanup` wired in v1, not deferred
The runner accepts `--cleanup` and, after metrics emit, deletes per-id (`DELETE /memory/<id>` for each eval-run-tagged record returned by the recall snapshot). Cheap to write, prevents corpus pollution from accumulating across iteration runs. (See finding C below for why per-id is the only option.)

**Rejected:** "ship without --cleanup, add later." 10 LOC saved is not worth the debt.

### 6. `/health` pre-flight in the runner, fail loud
Before firing any fixture, the runner GETs `localhost:8001/health`. If it doesn't return `{status: "healthy"}`, exit with a useful message. Saves 30s of confusion when someone forgets `docker compose up -d` in the sibling repo.

### 7. Single batch authoring of fixtures, not parallel
8 PostToolUse + 1 Stop fixture + 1 negative-control fixture, all with the same stdin schema. Authoring them via one task with the schema in front beats 9 parallel agents that drift on shape.

### 8. No `expand_relations` in the snapshot recall
Per project CLAUDE.md, server-side `expand_relations` is a no-op under tag gating; we filter by `eval-run-<uuid>` so any expansion would be filtered out. The runner sets `expand_relations: false` explicitly (or omits it).

### 9. Fixture schema is the canonical contract
Fixtures match the stdin shape the production hooks parse: `{tool_input: {command: str}, tool_response: {exit_code: int, ...} | str, cwd: str}` — verified at `mcp-automem/templates/claude-code/hooks/capture-build-result.sh:48-54`. The runner produces this shape; fixtures store it. Any deviation invalidates results.

### 10. Metrics computed post-hoc, not during hook execution
`hook_metrics.py` reads a snapshot JSON and emits a metrics JSON. Keeps the runner simple (just fire + drain + snapshot) and lets metrics evolve without re-running hooks.

## Implementation findings worth keeping

Found while building the runner. Each is a non-obvious property of the
production code path that future variant work should not rediscover.

### A. AutoMem `/recall` is GET with `X-Api-Key`, not POST + Bearer

The `/recall` endpoint uses **GET with query params** and the
`X-Api-Key` header (matches the existing `runners/compare_rulesets.py`
pattern). POST with `Authorization: Bearer` returns 405. POST `/memory`
silently accepted Bearer in testing — the runner uses `X-Api-Key`
everywhere for consistency.

### B. `/recall` response shape: `.results[].memory` not `.results[]`

Each result is `{id, score, score_components, memory: {content, tags, type, importance, metadata, ...}, relations, ...}`. The `id` is at top level; everything else is nested under `memory`. Snapshots store the full result objects so callers downstream can pull `.memory.<field>`.

### C. No `/memory/by-tag` endpoint — cleanup is per-id

`DELETE /memory/<id>` works; `DELETE /memory/by-tag?tag=X` 404s.
`cleanup_by_tag()` iterates the recall snapshot and deletes per-id.

### D. The deploy hook excludes `'unknown'` from tags but leaves it in content

`capture-deployment.sh` line 258: `if platform and platform != "unknown": tags.append(platform)` — but the content template (`Deployed X to Y on $DEPLOY_PLATFORM`) substitutes regardless. So the `'on unknown'` substring lands in content, then server-side NER hallucinates entity tags around it (e.g. `entity:organizations:deployed`). The audit's actual artifact is therefore in **content**, not tags. Updated `count_unknown_platform_in_content` accordingly.

### E. `process-session-memory.py` emits records with `tags: null, type: null`

Two of the seven baseline-run queue records have null tags/type because process-session-memory.py writes a different field shape than capture-*.sh. POSTs still succeed (server backfills); `type_validity.invalid_count` flags them as out-of-enum. Don't mistake this for a malformed JSON issue — it's a mis-typing issue at the hook layer, exactly what audit finding #5 flagged.

### F. `bash -n` and `python -m py_compile` aren't enough — fixture-driven smoke is the real gate

The hook scripts pass syntax check trivially but only the end-to-end smoke run exposes the bash/jq/python interaction (e.g. `tool_response` being either object-or-string in the jq expression). Don't ship a variant without firing fixtures through it.

## Out of scope (and where it goes)

- Layer 2 recall probes with Haiku + caching → separate PR.
- Bootstrap CIs → follow-up once we have ≥20 fixtures.
- CI integration → separate PR; repo has no CI yet.
- Touching mcp-automem → variant overlays only; mcp-automem PRs come after this harness validates fixes locally.

## Next steps after this PR merges

- `fix-v2-sanitize-content` variant (300-char hard cap + heredoc strip in `capture-test-pattern.sh` and `capture-build-result.sh`).
- `fix-v3-add-fields` variant (`confidence`, `originSessionId`, `t_valid`/`t_invalid`).
- `fix-v4-relations` variant (`relatesTo` for build-failure → recent edit chains).
