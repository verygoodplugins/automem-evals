# Session 2026-04-21 — BEAM 100K / 2-conv smoke

## Headline

**62.5% accuracy (25/40) at top_100, avg score 0.568, zero errors**, V1 pass-through
shim against the local AutoMem stack. Ingest + 40 gpt-5-judged questions completed
cleanly in one shot. These numbers are **signal, not a benchmark claim** — n=4 per
category is noisy, and the shim intentionally skips fact extraction. See
`data/results/beam/README.md` for the framing.

## Per-category breakdown

| Category                 | Accuracy       | Avg score |
| ------------------------ | -------------- | --------- |
| knowledge_update         | **4/4 (100%)** | 0.875     |
| preference_following     | 3/4 (75%)      | 0.750     |
| information_extraction   | 3/4 (75%)      | 0.708     |
| multi_session_reasoning  | 3/4 (75%)      | 0.688     |
| event_ordering           | 3/4 (75%)      | 0.683     |
| instruction_following    | 3/4 (75%)      | 0.625     |
| summarization            | 3/4 (75%)      | 0.504     |
| contradiction_resolution | 1/4 (25%)      | 0.344     |
| abstention               | 1/4 (25%)      | 0.250     |
| temporal_reasoning       | 1/4 (25%)      | 0.250     |

Every category returned some signal — no translation-bug blackhole. At n=4 per
category these numbers are too noisy to compare directly to mem0's published
numbers, and it would be misleading to put them side-by-side in a table that
might get screenshotted. For reference only, upstream's mem0-cloud BEAM 10M
results are the weakest on temporal_reasoning (16.3%), event_ordering (20.2%),
and multi_session_reasoning (26.1%); strongest on preference_following (90.4%)
and instruction_following (82.5%). Our smoke's weak spots are
temporal_reasoning, abstention, and contradiction_resolution — roughly the same
shape, though tier (100K vs 10M), sample size, and our pass-through ingestion
all cut against a real comparison. The argument for running a larger tier next
is that graph-shaped categories look at least _non-degenerate_ here even on raw
dialogue, which is what the session opener predicted.

## Cost + timing

- 40 questions × gpt-5 answerer + gpt-5 judge.
- Wall-clock: ~37 minutes for the question-answering phase (~55s/question avg).
  One question hit a 5-retry structured-output timeout and recovered.
- Ingestion was fast: both conversations ingested in under 20 seconds each
  (4–6 chunks/sec on /memory POSTs).
- 100 beam-tagged AutoMem memories were swept on teardown. Tag-gate isolation
  held throughout — no 405s in `shim.log`, no truncation warnings.
- $5.44 on GPT5

## What actually shipped this session

```
automem-evals/
├── third_party/memory-benchmarks/     # submodule @ f75666d
├── runners/
│   ├── beam_shim.py                   # mem0-OSS REST → AutoMem REST, stdlib
│   └── run_beam.py                    # preflight + wrapper, archives manifest
├── scripts/
│   └── beam_shim_smoke.py             # plumbing test
├── .venv-beam/                        # gitignored, holds upstream deps
└── data/results/beam/
    ├── README.md                      # "not a benchmark claim" stake
    └── 20260421-051827-100K-0_1/      # this run
        ├── MANIFEST.json              # command, upstream SHA, exit code
        ├── shim.log                   # empty except start/stop
        ├── beam_results_20260421_055555.json  # 19 MB of per-q reasoning
        └── beam-output/predicted_automem-20260421-051827/
```

## One resolved scare, documented for future me

Reviewer flagged a Feb-2026 memory claiming a 2000-char hard cap on
`POST /memory`. Probed directly: the real cap is **50,000 chars**, and upstream
BEAM pre-chunks ingestion with `CHUNK_SIZE = 2` turns, so real payloads are a
few KB. Belt-and-suspenders: the shim now logs + truncates at 49K
(`beam_shim.py:AUTOMEM_MAX_CONTENT`) so if BEAM ever changes chunking we hear
about it instead of silently failing.

## Next steps (in order of how I'd prioritize them)

1. **Run the full 100K bucket (20 conversations, ~400 questions).** Moves n-per-category
   from 4 to ~40 and turns "signal" into something that can support claims. Cost ~10×
   this smoke (~$20–40 OpenAI). Ask before executing — budget check.
2. **V2 extraction shim.** Replicate mem0-OSS's gpt-4o-mini fact extraction in the shim
   so AutoMem gets the same kind of input mem0 does. Measure lift on
   temporal_reasoning, contradiction_resolution, abstention — the weak categories here.
   If V2 materially improves those, the story becomes "AutoMem matches mem0 structurally
   once the pipelines are comparable," which is what the paper would need.
3. **Port to memorybench (`src/benchmarks/beam/`).** Once V1 or V2 numbers look durable,
   reimplementing BEAM in memorybench's TS framework unlocks cross-provider comparison
   without a shim. This is the paper-publishing path. Not needed until the above
   produces a result worth publishing.

## Not on the list (resisting the urge)

- `--top-k` sweep (10/20/50/200). Interesting, but wait until we have a bigger
  sample size — at n=4 it's noise.
- Per-question error analysis. 19 MB of judge reasoning is in the results file;
  dig in only if a specific category comes up in V2 planning.
- Changing AutoMem internals (decay, expand_relations, confidence gates) based on
  these numbers. 40 questions isn't enough signal to chase internal changes.
