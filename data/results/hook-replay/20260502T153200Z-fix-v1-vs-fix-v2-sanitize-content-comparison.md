# Hook-replay comparison: `fix-v1-no-session` vs `fix-v2-sanitize-content`

- **A: `fix-v1-no-session`** — eval-run `d14afd8622b5`, 5 queue records, 5 recalled.
- **B: `fix-v2-sanitize-content`** — eval-run `e063bda3f52c`, 5 queue records, 5 recalled.
- Generated: 2026-05-02T15:32:15+00:00

## Anti-pattern signatures (lower is better)

| metric | fix-v1-no-session | fix-v2-sanitize-content | delta |
|---|---:|---:|---:|
| session_summary_content | 0 | 0 |  |
| hallucinated_entity_tags | 0 | 0 |  |
| platform_unknown | 1 | 1 |  |
| serialized_tool_response | 2 | 0 | -2 ✓ |
| heredoc_fragments | 1 | 0 | -1 ✓ |

## Field presence (higher is better — fraction of records with field)

| metric | fix-v1-no-session | fix-v2-sanitize-content | delta |
|---|---:|---:|---:|
| with_confidence_pct | 0.0 | 0.0 |  |
| with_origin_session_id_pct | 0.0 | 0.0 |  |
| deploys_with_t_valid_pct | 1.0 | 1.0 |  |

## Content shape — length distribution

| bucket | fix-v1-no-session | fix-v2-sanitize-content | delta |
|---|---:|---:|---:|
| le_150 | 2 | 3 | +1 |
| 151_300 | 3 | 2 | -1 |
| 301_1000 | 0 | 0 |  |
| gt_1000 | 0 | 0 |  |
| near_duplicate_rate | 0.0 | 0.0 |  |

## Tag drift (lower is better)

| metric | fix-v1-no-session | fix-v2-sanitize-content | delta |
|---|---:|---:|---:|
| jest_collisions | 1 | 1 |  |
| date_derived_tags | 0 | 0 |  |

## Type validity

| metric | fix-v1-no-session | fix-v2-sanitize-content | delta |
|---|---:|---:|---:|
| valid_count | 5 | 5 |  |
| invalid_count | 0 | 0 |  |

## Verdict

**Improved by `fix-v2-sanitize-content`:**
- serialized_tool_response: 2 → 0
- heredoc_fragments: 1 → 0

**Untouched by this single-knob change** (out of scope for `fix-v2-sanitize-content`):
- session_summary_content (unchanged at 0)
- hallucinated_entity_tags (unchanged at 0)
- platform_unknown (unchanged at 1)
- type_validity.invalid_count (unchanged at 0)
- tag_drift.jest_collisions (unchanged at 1)
- tag_drift.date_derived_tags (unchanged at 0)
