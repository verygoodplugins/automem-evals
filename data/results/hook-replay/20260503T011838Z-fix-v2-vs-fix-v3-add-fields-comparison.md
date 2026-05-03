# Hook-replay comparison: `fix-v2-sanitize-content` vs `fix-v3-add-fields`

- **A: `fix-v2-sanitize-content`** — eval-run `4b1de8d0b1b7`, 5 queue records, 5 recalled.
- **B: `fix-v3-add-fields`** — eval-run `1b9d7c87a59d`, 5 queue records, 5 recalled.
- Generated: 2026-05-03T01:21:03+00:00

## Anti-pattern signatures (lower is better)

| metric | fix-v2-sanitize-content | fix-v3-add-fields | delta |
|---|---:|---:|---:|
| session_summary_content | 0 | 0 |  |
| hallucinated_entity_tags | 0 | 0 |  |
| platform_unknown | 1 | 1 |  |
| serialized_tool_response | 0 | 0 |  |
| heredoc_fragments | 0 | 0 |  |

## Field presence (fraction of records with field)

| metric | fix-v2-sanitize-content | fix-v3-add-fields | delta |
|---|---:|---:|---:|
| with_confidence_pct | 0.0 | 1.0 | +1.000 ✓ |
| with_origin_session_id_pct | 0.0 | 1.0 | +1.000 ✓ |
| with_t_valid_pct | 0.4 | 1.0 | +0.600 ✓ |
| with_t_invalid_pct | 0.0 | 0.0 |  |
| deploys_with_t_valid_pct | 1.0 | 1.0 |  |

## Content shape — length distribution

| bucket | fix-v2-sanitize-content | fix-v3-add-fields | delta |
|---|---:|---:|---:|
| le_150 | 2 | 2 |  |
| 151_300 | 3 | 3 |  |
| 301_1000 | 0 | 0 |  |
| gt_1000 | 0 | 0 |  |
| near_duplicate_rate | 0.0 | 0.0 |  |

## Tag drift (lower is better)

| metric | fix-v2-sanitize-content | fix-v3-add-fields | delta |
|---|---:|---:|---:|
| jest_collisions | 1 | 1 |  |
| date_derived_tags | 0 | 0 |  |

## Type validity

| metric | fix-v2-sanitize-content | fix-v3-add-fields | delta |
|---|---:|---:|---:|
| valid_count | 5 | 5 |  |
| invalid_count | 0 | 0 |  |

## Verdict

**Field presence improved by `fix-v3-add-fields`:**
- with_confidence_pct: 0.0 -> 1.0
- with_origin_session_id_pct: 0.0 -> 1.0
- with_t_valid_pct: 0.4 -> 1.0

**Untouched by this single-knob change** (out of scope for `fix-v3-add-fields`):
- session_summary_content (unchanged at 0)
- hallucinated_entity_tags (unchanged at 0)
- platform_unknown (unchanged at 1)
- serialized_tool_response (unchanged at 0)
- heredoc_fragments (unchanged at 0)
- type_validity.invalid_count (unchanged at 0)
- tag_drift.jest_collisions (unchanged at 1)
- tag_drift.date_derived_tags (unchanged at 0)
