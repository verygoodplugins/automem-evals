# Session 2026-06-10/11 — Production entity-tag repair (issue #72 rollout)

The staged repair that PR automem#176 tooling + this repo's PR #8 harness were built for
finally ran against production (`https://automem.up.railway.app`, ~10,090 memories).
All artifacts under `data/sweep_runs/prod-rollout-20260610/`.

## Outcome

| Stage | Result |
|---|---|
| 3A reject-only | 6,106 noise entity tags removed across 7,912 memories; 0 failures; re-audit `changed=0` |
| 3B canonicalize-safe | 121 rewrites (101 possessive strips @0.95, 20 single-name @0.6) + 1,584 ambiguous single-name people suppressed across 1,283 memories; re-audit `changed=0` |
| Post-verify | `/entities/audit` rejected **7,5xx → 0** (7,133 accepted); `/health` synced 10,092/10,092; Qdrant payload parity 5/5 |
| Entity-node migration | **DEFERRED at Gate 5** — dry-run accepted 1,591 (1,020 people, of which 734 single-reference ≈80% word-pair noise) |

Single-name people removed per the approved ambiguity policy: `jack` ×1,320 total
(630 reject + 690 ambiguous), plus a second ambiguous first name ×313. `jack-arturo`
carries the canonical entity.

Safety nets kept: `rollback.jsonl` for both stages (copied out of the container —
Railway fs is ephemeral), pre-repair snapshot `prod-api-20260610-201302`, post-repair
snapshot `prod-api-20260611-post-repair-*`.

## The Gate 3 stop-the-line story (two validator PRs)

1. First prod dry-run planned **7,677** rejections; review found ~1,600 legitimate
   (725 distinct real people, e.g. jack-arturo).
   Root causes: context-hint branch condemned any person mentioned near
   data/project/tool words; `"code"` token rejected claude-code/vs-code; missing
   events/opportunities categories.
2. **PR #178** fixed it — but an applied Copilot suggestion (committed via "apply
   suggestion" before merge) gated the person-shape exemption on the value containing
   a space. Stored tags only have slugs → the repair path (`validate_entity_tag`)
   never fired the exemption. Prod dry-run v2: 7,494 (expected ~6,106). CI stayed
   green because every test exercised the spaced-value path.
3. **PR #179** restored the plain exemption, addressed the bot's actual concern
   (`data-dog`) via `_NON_PERSON_TECH_TOKENS`, and added slug-path-with-context
   regression tests. Prod dry-run v3: **6,106 — byte-identical to the reviewed local
   expectation** (0 set diff). A second Copilot suggestion on #179 was *good* (made
   the regression test context actually mention the person) and was kept.

Lesson: review-bot suggestions applied at the last minute can silently regress the
exact path under repair; the dry-run-diff-against-reviewed-expectation gate caught it.

## Surprise discovery: Qdrant payload drift was distorting recall

Pre-repair, many Qdrant payloads carried entity tags that were **never in the graph**
(e.g. `entity:organizations:woocommerce` on `7f850a97`/`447356fe` payloads only).
The repair's `sync_qdrant_payload` healed payloads to graph truth, and recall probes
*improved*: the WP-FUSION probe's objectively-correct memories went from absent to
ranks 1–2 (score 0.73 vs old top 0.57); the LoCoMo probe's top-3 became the actual
LoCoMo milestone/status memories. Probe rows flagged REGRESSION/review by the runner
were all explained by (a) intended noise-entity cleanup, (b) payload-drift healing,
(c) noise probes returning fewer junk rows (`SESSION-MILESTONE-NOISE` 7→0). No bare
tag was touched anywhere (plan invariant verified: 0 across all 7,912+1,283 rows).

## Operational notes

- `railway ssh -- '<one raw string>'` is the working quoting pattern; `sh -c '…'`
  loses quoting. Artifact exfil: `gzip -c FILE | base64` then decode locally.
- In-container FalkorDB: `FALKORDB_PASSWORD` env is whitespace — the repair script's
  `_get_env` strips it to None; raw `os.environ.get` AUTHs and fails. Mimic `_get_env`.
- Admin endpoints need `Authorization: Bearer $AUTOMEM_API_TOKEN` **and**
  `X-Admin-Token: $ADMIN_API_TOKEN`.
- Execute-vs-live-writes mitigation worked as designed: regenerate plan → diff vs
  reviewed (tag-action delta was 0 both stages) → execute → re-audit `changed=0`.
- Known harness bug (still open): `real_data_entity_repair_eval.sh` exits 0 even when
  `restore_from_backup.py` fails (observed during rehearsal prep, June 10).

## Follow-ups

- People-entity migration deferred: needs a word-pair-noise validator pass or a
  `--min-references`/`--categories` gate on `migrate_entity_nodes.py` (Gate 5 data:
  refs=1 people ≈80% noise; even refs≥2 leaks `google-calendar`, `mile-method`, …).
- Residual verb-person fragments survive as tags (`needs-jack` and similar
  verb-firstname pairs) plus 8 noise canonical targets (`solana-agent`, `locomo-benchmark`,
  `rag-implementation`, …) — consolidated, low-impact, cleanable in the same future pass.
- Issue #72 comment + PR #124 disposition: see Gate 6.
- Consider removing the Railway SSH key added for this rollout (`railway ssh keys`).
