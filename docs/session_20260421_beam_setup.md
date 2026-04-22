# Session 2026-04-21 — BEAM via shim: setup complete, smoke pending

## Status

Plumbing wired, not yet exercised end-to-end. The 100K / 2-conversation smoke
is blocked only on `OPENAI_API_KEY` being set in the caller's shell. Every
other piece round-trips cleanly.

## What was built

```
automem-evals/
├── third_party/memory-benchmarks/   # submodule @ f75666d (mem0ai/memory-benchmarks)
├── runners/
│   ├── beam_shim.py                 # stdlib HTTP shim; mem0-OSS REST → AutoMem REST
│   └── run_beam.py                  # wrapper: preflight, spawn shim, run BEAM, sweep
├── scripts/
│   └── beam_shim_smoke.py           # round-trip test; passed twice locally
├── data/results/beam/
│   └── README.md                    # "not a benchmark claim" stake + V1 caveat
└── .venv-beam/                      # gitignored; holds upstream BEAM's deps
```

## Upstream contract (verified, not guessed)

Read straight from
`third_party/memory-benchmarks/benchmarks/common/mem0_client.py`. Three
endpoints on the OSS path:

| Upstream call                | HTTP                                               | Translated to                                          |
|------------------------------|----------------------------------------------------|--------------------------------------------------------|
| `mem0.add(messages, user_id)` | `POST /memories`                                  | `POST /memory` with `tags=[user_id, "beam"]`           |
| `mem0.search(query, user_id, top_k)` | `POST /search`                             | `GET /recall?query=&tags=<user_id>&limit=<top_k>`      |
| `mem0.delete_user(user_id)`  | `DELETE /memories?user_id=...`                    | Recall-by-tag, delete each                             |

The shim rejects anything outside this list with 405. Trust-but-verify pattern
— if the upstream adds a field we don't handle, we hear about it immediately.

## V1 caveat (documented loudly)

Real mem0-OSS runs an LLM fact extraction pass (`gpt-4o-mini` by default)
before writing. This V1 shim does **raw conversation pass-through** — each
`/memories` POST concatenates messages into one content blob and stores that
in AutoMem. Consequences:

- AutoMem retrieves from chat-formatted dialogue, not extracted facts.
- Noisier embeddings; coarser per-memory granularity.
- Cheaper on ingest (we save the `gpt-4o-mini` extraction spend).

If V1 scores come in low in graph-shaped categories (event_ordering,
multi_session_reasoning, contradiction_resolution), V2 is: replicate the
fact-extraction step in the shim. Captured in
`data/results/beam/README.md`.

## Content-size investigation (advisor-flagged, resolved)

Reviewer raised the Feb-2026 memory claiming a 2000-char hard limit on
`POST /memory`. Verified directly:

```
size=1900:  201 (ok)
size=2100:  201 (ok)
size=10000: 201 (ok)
size=50000: 400 — "Content exceeds maximum length of 50000 characters"
```

Real cap is **50,000 chars**, not 2,000. The old memory is stale on the
number, correct on the existence of a limit.

Follow-through: BEAM upstream pre-chunks ingestion with `CHUNK_SIZE = 2`
(`benchmarks/beam/run.py:89`). Every `/memories` POST the shim receives has
at most 2 conversation turns, typically a few KB. In practice we stay well
under the 50K cap. Belt-and-suspenders: shim now logs a WARN and truncates
to 49K if any single chunk ever exceeds the cap (`beam_shim.py:AUTOMEM_MAX_CONTENT`).
If that warning ever fires at scale, proper multi-memory chunking per chunk
is the next iteration.

## What the user runs next

```bash
# one-time (done):
git submodule update --init
python3 -m venv .venv-beam
.venv-beam/bin/pip install -r third_party/memory-benchmarks/requirements.txt 'datasets>=2.14'

# the smoke (~$2, per plan confirmation):
export OPENAI_API_KEY=sk-...
python3 runners/run_beam.py --tier 100K --conversations 0-1
```

Note on `datasets>=2.14`: upstream BEAM lazily imports `datasets` for the
HuggingFace pull but does not list it in `requirements.txt`. First run
without it fails at dataset download with a `pip install datasets` hint.
The one-liner above installs it preemptively.

Output lands at `data/results/beam/<ts>-100K-0_1/`:
- `MANIFEST.json` — timestamp, upstream SHA, full command, exit code
- `shim.log` — shim subprocess log
- `beam-output/predicted_<project>/*.json` — per-question artifacts
- `beam_results_*.json` — aggregated scores (if judge stage completed)

## Verified round-trip

Ran `scripts/beam_shim_smoke.py --self-spawn` twice — green both times:

```
[1/5] /health round-trip
[2/5] POST /memories (user_id=beam-shim-smoke)
       stored memory id: 47527a6b-ca9f-4a39-bbac-585d7e3bcfca
[3/5] POST /search ('What color did the user say their bike was painted?')
       top hit score=3.015 id=47527a6b-ca9f-4a39-bbac-585d7e3bcfca
[4/5] direct AutoMem recall confirms tag gate
       AutoMem sees 1 memory under tag=beam-shim-smoke
[5/5] DELETE /memories?user_id=beam-shim-smoke
       deleted 1 memories for beam-shim-smoke
       AutoMem confirms cleanup
```

Tag-gate isolation is working. Cleanup path works. AutoMem returns its
nested `{memory: {content, id}, score}` shape and the shim flattens it to
mem0's expected `{id, memory, score}` before returning — checked by the
smoke's top-hit assertion.

## Hard stop criteria for the real run

Per plan:
- If `jq '.scores | to_entries | map(select(.value > 0)) | length' …/beam_results_*.json`
  is zero, do not scale up. Something in translation is silently losing data.
- Do not run 1M or 10M without explicit approval. Cost scales ~10× per tier.

## TODO (post-smoke, in a follow-up session)

- Fill in per-category scores, cost, timing here.
- Note any new endpoints the upstream tried to call (shim logs will show 405s).
- Propose V2 extraction shim if graph-shaped categories underperform.
