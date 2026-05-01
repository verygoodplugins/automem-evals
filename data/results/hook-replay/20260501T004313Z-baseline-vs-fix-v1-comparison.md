# Hook-replay comparison: `baseline` vs `fix-v1-no-session`

- **A: `baseline`** — eval-run `5c22a1f9a9c0`, 7 queue records, 7 recalled.
- **B: `fix-v1-no-session`** — eval-run `410f3a5c62ea`, 5 queue records, 5 recalled.
- Generated: 2026-05-01T00:43:13+00:00

## Anti-pattern signatures (lower is better)

| metric | baseline | fix-v1-no-session | delta |
|---|---:|---:|---:|
| session_summary_content | 1 | 0 | -1 ✓ |
| hallucinated_entity_tags | 0 | 0 |  |
| platform_unknown | 1 | 1 |  |

## Field presence (higher is better — fraction of records with field)

| metric | baseline | fix-v1-no-session | delta |
|---|---:|---:|---:|
| with_confidence_pct | 0.0 | 0.0 |  |
| with_origin_session_id_pct | 0.0 | 0.0 |  |
| deploys_with_t_valid_pct | 1.0 | 1.0 |  |

## Content shape — length distribution

| bucket | baseline | fix-v1-no-session | delta |
|---|---:|---:|---:|
| le_150 | 3 | 2 | -1 |
| 151_300 | 4 | 3 | -1 |
| 301_1000 | 0 | 0 |  |
| gt_1000 | 0 | 0 |  |
| near_duplicate_rate | 0.0 | 0.0 |  |

## Tag drift (lower is better)

| metric | baseline | fix-v1-no-session | delta |
|---|---:|---:|---:|
| jest_collisions | 1 | 1 |  |
| date_derived_tags | 0 | 0 |  |

## Type validity

| metric | baseline | fix-v1-no-session | delta |
|---|---:|---:|---:|
| valid_count | 5 | 5 |  |
| invalid_count | 2 | 0 | -2 ✓ |

## Verdict

**Improved by `fix-v1-no-session`:**
- session_summary_content: 1 → 0
- type_validity.invalid_count: 2 → 0

**Untouched by this single-knob change** (out of scope for `fix-v1-no-session`):
- hallucinated_entity_tags (unchanged at 0)
- platform_unknown (unchanged at 1)
- tag_drift.jest_collisions (unchanged at 1)
- tag_drift.date_derived_tags (unchanged at 0)
