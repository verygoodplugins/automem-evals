# Session 2026-06-13 - BEAM retrieval-proxy 100K full bucket

Run ID: `20260613-100k-full-retrieval-proxy`

This is a deterministic AutoMem `/recall` retrieval-proxy result from
`runners/beam_retrieval_eval.py`, not an official BEAM end-to-end score. No
answerer model or judge model was invoked.

## Scope

| field | value |
|---|---:|
| BEAM tier | `100K` |
| dataset source | cached `third_party/memory-benchmarks/datasets/beam/beam_100K.json` |
| conversations | 20 |
| questions | 400 |
| AutoMem memories seeded | 29,902 |
| `OCCURRED_BEFORE` associations | 29,882 |
| recall limit per question | 50 |

The run artifacts were written locally under:

```text
data/results/beam-retrieval/20260613-100k-full-retrieval-proxy/
```

Raw per-run artifacts are ignored by git; this note is the curated record.

## Result

| metric | value |
|---|---:|
| proxy pass rate | 75.5% |
| mean proxy score | 0.6013 |
| mean rubric overlap | 0.4301 |
| source-chat hit rate | 85.1% |
| source-chat denominator | 355 |
| abstention evidence-absence rate | 0.0% |
| abstention denominator | 40 |

## By Ability

| ability | n | pass | proxy | rubric | source hit | abstention absent |
|---|---:|---:|---:|---:|---:|---:|
| abstention | 40 | 0.0% | 0.0000 | 0.6525 | n/a | 0.0% |
| contradiction_resolution | 40 | 100.0% | 0.7435 | 0.3589 | 100.0% | n/a |
| event_ordering | 40 | 75.0% | 0.7032 | 0.6330 | 75.0% | n/a |
| information_extraction | 40 | 90.0% | 0.7257 | 0.4643 | 90.0% | n/a |
| instruction_following | 40 | 42.5% | 0.3814 | 0.3159 | 42.5% | n/a |
| knowledge_update | 40 | 97.5% | 0.7592 | 0.4356 | 97.5% | n/a |
| multi_session_reasoning | 40 | 97.5% | 0.7406 | 0.3891 | 97.5% | n/a |
| preference_following | 40 | 75.0% | 0.5899 | 0.3373 | 76.9% | n/a |
| summarization | 40 | 77.5% | 0.6229 | 0.3478 | 86.1% | n/a |
| temporal_reasoning | 40 | 100.0% | 0.7466 | 0.3664 | 100.0% | n/a |

## Validation

Pre-run AutoMem health was healthy and synced at 10,107 memories/vectors. After
ingest, health was healthy and synced at 40,009 memories/vectors, exactly
matching the manifest delta of 29,902 seeded memories.

A validation script checked:

- manifest schema and result schema
- `run_id`, dataset repo, and `100K` split consistency
- 20 conversations, 20 questions per conversation, 400 unique question IDs
- 29,902 unique manifest memory IDs
- 29,882 associations, equal to `memory_count - conversation_count`
- every result question ID matched the manifest question set
- every top retrieved memory ID belonged to the run manifest
- `source_chat_hit` matched source/retrieved source-ID intersections
- `passed` matched `proxy_score >= 0.5`
- recomputed aggregates matched the stored aggregate
- regenerated report matched `report.md`
- every BEAM ability category had 40 questions

After validation, `scripts/beam_cleanup.py` deleted 29,902 memories tagged
`beam-run-20260613-100k-full-retrieval-proxy`. A follow-up exact-tag recall
returned 0 results, and AutoMem health returned to 10,107 synced
memories/vectors.

## Interpretation

The result is accurate for the retrieval-proxy metric implemented in this repo.
It should not be compared as an official BEAM score against systems that run
BEAM's answer generation and judge pipeline.

The abstention category is intentionally harsh in this proxy: the runner treats
retrieved overlapping conversation snippets as evidence presence, even when the
official BEAM answer would still need to abstain because the missing detail is
not actually available. Use that line as a retrieval false-positive signal, not
as an answerability judgment.
