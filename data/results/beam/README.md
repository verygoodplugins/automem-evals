# BEAM runs — experimental, not a benchmark claim

Every artifact in this directory comes from `runners/run_beam.py`, which wraps
mem0's upstream BEAM runner and drives it at our local AutoMem stack through a
thin HTTP shim (`runners/beam_shim.py`).

**These numbers are not benchmark claims.** Do not quote them externally.
The shim's current (V1) design is documented to have a material asymmetry vs.
the upstream mem0-OSS pipeline — see below — so scores here under-measure
AutoMem's ceiling, not over-measure it.

## V1 shim caveat

The real mem0-OSS server runs an LLM **fact extraction** pass (default
`gpt-4o-mini`) before it writes memories. Our V1 shim does a raw conversation
pass-through: each `POST /memories` call concatenates the messages into one
content block and stores that directly in AutoMem.

Consequences:
- AutoMem is being asked to retrieve from chat-formatted dialogue, not from
  pre-extracted facts. Embeddings on raw dialogue are noisier.
- Per-memory granularity is coarser — one AutoMem memory per message batch,
  not N extracted facts per batch.
- `gpt-4o-mini` cost savings on the ingest side; everything else (answerer,
  judge) is identical to upstream.

A V2 shim that replicates extraction is the obvious next step if V1 scores
look weak in graph-shaped categories (event_ordering, multi_session_reasoning,
contradiction_resolution) — those are the ones that should most benefit from
cleaner per-fact memories.

## Where results can end up

| Path | Status | Use |
|---|---|---|
| This directory (`automem-evals/data/results/beam/`) | **Experimental**, never a benchmark claim. | Session-bounded signal for whether BEAM is worth investing in against AutoMem. |
| `memorybench/src/benchmarks/beam/` (future) | Cross-provider comparisons via the existing pluggable framework. | Compare AutoMem vs. mem0-OSS vs. Zep, etc. on the same BEAM data. |
| `automem/` official harnesses (future) | Release-gated, paper-facing. | Only after an approach here reproduces cleanly and a decision is made to publish. |

Promotion flows up the chain, never down. Numbers that live only here stay
here.

## Directory shape per run

Every `run_beam.py` invocation creates:

```
<ts>-<tier>-<convs>/
├── MANIFEST.json         # timestamp, tier, conversations, upstream SHA, full command
├── shim.log              # stdout+stderr of the shim subprocess
└── beam-output/
    ├── predicted_<project>/   # BEAM's per-question JSON artifacts (upstream layout)
    └── beam_results_*.json    # aggregated summary (when the judge stage completes)
```

Aggregated scores end up in `beam_results_*.json`; per-question reasoning
lives under `predicted_<project>/`.
