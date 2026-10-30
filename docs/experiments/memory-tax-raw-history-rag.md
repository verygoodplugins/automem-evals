# Memory Tax: raw-history RAG control (`EXP-MEMORY-TAX`)

Status: **spec only. No paid run is authorized.** Exploratory and internal; official benchmark
claims stay in `automem` ([REPO_BOUNDARY](../REPO_BOUNDARY.md)). Written 2026-10-30.

## 1. Question

He et al., ["Memory Tax: Dissecting the Net Value of Agent Memory"](https://arxiv.org/abs/2610.34073)
(arXiv v1, 2026-10-25; [project page](https://hexuan21.github.io/MemoryTax/)) report that many
dedicated memory systems score below naive RAG over raw history, and that retrieving from raw
history alongside memory ("src-aug") recovers some of the loss. Those are the paper's claims, not
AutoMem results. Paper figures must be labelled as paper baselines in any report here.

This spec asks the AutoMem version on the existing LongMemEval-S harness (primary) and BEAM 100K
(gated):

> Do AutoMem's write-time processing, lifecycle suppression (`t_invalid`, `INVALIDATED_BY`,
> `EVOLVED_INTO`) and graph expansion cost answer accuracy versus plain retrieval over the same raw
> history, with the reader, judge, prompt, embedder and context budget held fixed?

Motivation: PR #78 shows inline obsolete content leaking through `/recall` relations. The inverse
risk is lifecycle suppression hiding evidence that raw retrieval would have returned.

## 2. Relation to existing threads (dedup decision)

A search of both repos on 2026-10-30 found **0** issues/PRs matching "Memory Tax" or "MemoryTax" in
`automem-evals` and in `automem`. Related, not duplicate:

| Ref | What it is | Relationship |
| --- | --- | --- |
| #48 / PR #49 | MemDelta-controlled baselines on LongMemEval-S (`no-memory`, `verbatim-rag`, `full-context`, `automem`; C0/C1/C2) | Closest. Arm (a) is meant to coincide with #48's `verbatim-rag` under the same frozen contract. New here: paired per-question benefit/tax, cause tags, arm (c). Confirm that mapping, and map P0/P1 to C0..C2, once #49's protocol doc lands (not on `main` yet). |
| #50 | StateMemBench, current vs superseded state | Complements the `invalidation_hiding` cause. |
| #74 | FEB-30 intrinsic store-state adapter, blocked on release | Would give an independent `write_drop` measurement. |
| PR #78 / automem#273 | Inline obsolete suppression | Motivation; also the server sensitivity pin (section 3). |
| #54 | LongMemEval-V2 web-agent benchmark | Separate benchmark per its own text; not related. |
| #73 | Merged dashboard refresh PR | Not AMB; no overlap. |

Decision: one new tracking issue for the analysis plus a cross-link comment on #48. Neither is posted
by this change; bodies are in the handoff.

## 3. Pins

| Item | Pin |
| --- | --- |
| Paper | arXiv:2610.34073v1, submitted 2026-10-25 |
| Paper code | `https://github.com/hexuan21/MemoryTax` @ `179e6a79da415a4e1eabe9eb3110754955360d05` (`main`, 2026-10-27T03:20:54Z, MIT, 16 commits, no tags or releases) |
| Paper results | HF `hexuan21/MemoryTax-Res` @ `83a3e9d813875705b96b390b578c7c02f0fabe01` (cc-by-4.0). The root repo is an index with no data files; it links six result repos of 0.1-49.1 GB, none downloaded or inspected |
| AutoMem server (primary) | `3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876`, the frozen post-merge candidate behind 427/500 |
| AutoMem server (sensitivity) | `fe0d5c374f1da65d30aaa9311e24647284d22793` (adds #273 inline suppression) |
| Official LME harness | `tests/benchmarks/longmemeval` at the primary server pin, `--config baseline` |
| Eval harness base | `f0abc8a46646971ae62717a498a7338f6b23b24e` |
| LME-S dataset | `longmemeval_s_cleaned.json` from HF `xiaowu0162/longmemeval-cleaned`; 277,383,467 bytes, sha256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` (local copy; HF revision not recorded, Stage 0 must record it) |
| Reader | `gpt-5-mini`. It is an alias, not a snapshot: record the served model string per call |
| Judge | `gpt-5.4-mini-2026-03-17`, profile `openai-gpt-5.4-mini-2026-03-17` ([policy](../BENCHMARK_JUDGE_POLICY.md)) |
| Embedder | `voyage-4`, 1024d, for both AutoMem and the raw arm |
| Services | FalkorDB v4.18.10, Qdrant v1.11.3, `PYTHONHASHSEED=0` (from the [post-merge baseline](../session_20261022_postmerge_baseline.md)) |
| BEAM harness | `runners/beam_judged_eval.py`; submodule `third_party/memory-benchmarks` @ `f75666d33ef560f0f196746e0e16c515d17e6856` |
| Python | `python3.12` (3.12.13). The default macOS `python3` is 3.9.6 and gives 10 errors across the four Stage 0 suites (`datetime.UTC`, `X \| None` annotations); all pass under 3.12. `scripts/experiment_index.py` needs 3.11+ |

### Paper-code release status

Checked 2026-10-30 against the pinned commit. **Partially released; do not depend on it.**

- Present: `common/bench/{download,prepare}.py`, `common/bench/subset_ids/longmemeval_s_sub100.json`,
  `common/judge/prompts.py`, `common/qa_prompts/qa_longmemeval.py`, `common/api/` (README only).
- Absent: runnable baselines. The README TODO "Release reproduction codes of each baseline" is
  unchecked and the Quickstart says `# TODO: harness commands`. `reproduction/_naive_rag/` holds one
  149-byte README. The project page names naive RAG (RAG-Emb, RAG-Hybrid, IDF-keyword) but gives no
  retriever, chunking, top-k, reader or judge settings. `src-aug` is not in the repo README.
- Consequence: arms (a) and (c) are defined here from first principles and the page text. This spec
  does not reproduce the paper's numbers and claims no parity.
- Re-check before any report: `git ls-remote https://github.com/hexuan21/MemoryTax.git refs/heads/main`.
  If the SHA moved, re-read the TODO list and `reproduction/_naive_rag/`, then update this table.

## 4. Arms

All arms share: dataset order, question text as the only query, one retrieval unit = one haystack
session (identical bytes to the harness `per-session` payload), context budget **top-10**
(`recall_limit=10`, matching `--config baseline`), the chain-of-note prompt
(`answer_focus_prompt=false`, `temporal_answer_hint=false`), the same reader and judge.

| Arm | Retrieval | Notes |
| --- | --- | --- |
| (a) `raw` | Cosine top-10 over raw sessions embedded with `voyage-4` | No tag gate, time window, graph or lifecycle. Isolation is by construction: only that question's sessions are indexed |
| (b) `automem` | Unmodified harness `/recall` at the server pin | Reuse the existing 427/500 per-question results only if the Stage 0 identity check passes; else rerun |
| (c) `fused` | Union of (b) top-10 and (a) top-10, deduped by `session_id`, reranked by Reciprocal Rank Fusion (k=60), truncated to top-10 | Deterministic, no extra model or cost. Ties: raw cosine, then session date. A cross-encoder reranker is deliberately not chosen here, so a lift cannot be a stronger-reranker effect |

Declared differences, recorded not hidden: (b) applies `_extract_temporal_bounds` start/end and the
`longmemeval:<question_id>` tag gate; (a) does not. Any loss from those is tagged `retrieval_other`.

Optional equal-context sensitivity: (c) at top-20 against (b) `--config high-k`, to separate "more
context" from "different evidence".

### Store profiles

The `baseline` harness stores each ~10k-character session verbatim. With server defaults
(`MEMORY_CONTENT_SOFT_LIMIT=500`, `MEMORY_CONTENT_HARD_LIMIT=2000`, `MEMORY_AUTO_SUMMARIZE=true`)
those stores would be summarized or rejected, so the frozen baseline must have overridden them (as
automem's `scripts/bench/ingest_and_snapshot.sh` does: `MEMORY_CONTENT_HARD_LIMIT=50000
MEMORY_AUTO_SUMMARIZE=false`). Read the exact values from the retained bootstrap
(`data/sweep_runs/postmerge-20261022/final-paid-credits09v2/api_bootstrap_v2.py`) in Stage 0.

| Profile | Write path | Expected exposure |
| --- | --- | --- |
| P0 `cold-baseline` | Raw sessions, enrichment/JIT/consolidation off (the 427/500 setup) | Closest AutoMem gets to raw RAG. Acts as a negative control: a large tax here points at retrieval config, not memory processing |
| P1 `write-path-on` | P0 plus enrichment, `JIT_ENRICHMENT_ENABLED=true`, consolidation (exact env set recorded in Stage 0); run `baseline` and `full-graph` | Write-time edges, lifecycle suppression, expansion noise. Declare cold vs matured per [#18](https://github.com/verygoodplugins/automem-evals/issues/18); never mix within one comparison |
| P2 `production-limits` | `--config per-turn`, default soft/hard limits, auto-summarize on | `write_drop` from summarization. Canary only unless separately approved |

Stage 0 must run a **store-state census** on a few questions per profile: count edges by type,
memories with `t_invalid` or `archived`, and `metadata.was_summarized`. A cause that cannot occur
under a profile (for example zero lifecycle edges in P0) is reported as structurally absent, not as
"no effect".

## 5. Definitions

Per question q, `y_x(q)` is the judge's `is_correct` for arm x.

- `benefit(q) = [y_b=1 and y_a=0]`; `tax(q) = [y_b=0 and y_a=1]`; `net = acc_b - acc_a`.
- Report both counts, the 2x2 discordance table, exact two-sided McNemar p, paired bootstrap 95% CI
  (10,000 resamples, seed 0), overall and for the six question types.
- Primary contrast, fixed before any run: overall `acc_b - acc_a` under P0 and P1. Per-type results
  are secondary with Holm correction.
- Arm (c): recovery = share of tax cases with `y_c=1`; regression = `[y_b=1 and y_c=0]` over `acc_b*N`.
- **Noise floor.** Repeat reader+judge on identical prompts. Canary: two repeats of (a) and (b).
  Full run: three repeats on tax cases only. Claim a stable tax only for cases that flip in every repeat.
- Also report context tokens and recall latency per arm, and the #48 `controlled_evaluation` block
  (unknown stays `null`, never `0`).
- BEAM uses official pass/fail (`score >= 0.5`) so the definitions match. Mean nugget-score deltas
  are secondary.

## 6. Tax cause tags

Deterministic and trace-based; no LLM labelling. Gold = LongMemEval `answer_session_ids` (and the
`has_answer` turns inside them); BEAM uses `source_chat_ids`. Each tax case gets every flag that
fires plus one primary tag from the first matching rule:

1. **`write_drop`** (evidence dropped at write time). Fetch each gold session's stored memory via
   `GET /memory/<id>`. Fire if the memory is missing, the store call failed, `metadata.was_summarized`
   is true (server writes `was_summarized`, `original_content`, `original_length`), or any
   `has_answer` turn text is absent from stored `content`.
2. If any gold session is not in the (b) context, probe it:
   - **`invalidation_hiding`**: re-issue the identical `/recall` with `state_mode=history` and
     `state_debug=true`. Fire if the gold session now enters top-10; record the suppression reason
     (`archived`, `not_yet_valid`, `expired`, or replaced via `INVALIDATED_BY`/`EVOLVED_INTO`).
   - **`graph_noise`**: only where `expand_relations` or `expand_entities` was on. Drop
     expansion-only results from the saved response. Fire if the gold session re-enters top-10.
   - **`retrieval_other`**: otherwise (tag gate, time window, ranking, `recall_limit`). Sub-tag
     `time_window` if removing `start`/`end` recovers it.
3. If all gold sessions are in the (b) context:
   - **`abstention`**: `check_abstention_response(hypothesis)` is true on a non-`_abs` question
     (`over_abstain`), or the question is `_abs` and (b) answered instead of abstaining
     (`under_abstain`).
   - **`reader_noise`**: otherwise. Excluded from the tax claim unless it survives the noise floor.

Probes call `/recall` directly, because the harness backend does not expose `state_mode`. Report the
cause histogram overall and per type, each cause's share, and how much of it arm (c) recovers.

## 7. Stages and commands

Gates: **G0** this spec merged. **G1** owner approves the Stage 1 cap. **G2** Stage 1 review
(census, noise floor, cause plausibility) then approve Stage 2. **G3** Stage 2 review then approve BEAM.

Commands marked *(new)* do not exist yet; their slices are listed in section 10. Paths assume the
repository-root checkout with `automem` as a sibling (`../automem`), as in `CONTRIBUTING.md`; run the
harness with automem's `.venv` interpreter if present, as its launcher does.

### Stage 0: free, local, no API calls

```bash
python3.12 -m unittest discover -s runners -p 'test_*.py'
python3.12 -m unittest discover -s scripts -p 'test_*.py'
python3.12 -m unittest discover -s scripts/benchmarks -p 'test_*.py'
python3.12 -m unittest discover -s data/results/postmerge-20261022 -p 'test_*.py'

git -C ../automem rev-parse '3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876^{commit}'
git ls-remote https://github.com/hexuan21/MemoryTax.git refs/heads/main   # expect 179e6a79...
shasum -a 256 ../automem/tests/benchmarks/longmemeval/data/longmemeval_s_cleaned.json  # expect d6f21ea9...
```

Also in Stage 0: the identity check for reusing (b) (same dataset sha, reader string, judge,
prompt flags, `recall_limit`, embedder, server SHA, limit overrides), the census, and fixture tests
for the pairing and cause-tagging code.

### Stage 1: canary (30 questions, `--per-type 5`)

```bash
git -C ../automem worktree add ../automem-memtax 3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876
python3.12 scripts/benchmarks/paid_budget_proxy.py --ledger /abs/memtax-s1.sqlite3 \
  --pricing /abs/prices.json --cap-usd <APPROVED_STAGE_1_CAP>
# stack from ../automem-memtax with the Stage 0 limit overrides, then, per arm:
PYTHONHASHSEED=0 python3.12 runners/memory_tax/run_lme.py \
  --automem-repo /abs/automem-memtax --arm <raw|automem|fused> \
  --config baseline --per-type 5 --llm-eval \
  --llm-model gpt-5-mini --eval-llm-model gpt-5.4-mini-2026-03-17 \
  --output /abs/out/lme-canary-<arm>                                   # (new)
python3.12 runners/memory_tax/pair.py --a /abs/out/lme-canary-raw.json \
  --b /abs/out/lme-canary-automem.json --c /abs/out/lme-canary-fused.json  # (new)
python3.12 runners/memory_tax/diagnose.py --pairs <pair-output> \
  --automem-repo /abs/automem-memtax                                   # (new)
```

`run_lme.py` imports the pinned harness and swaps `create_backend`, the same seam the harness's own
tests use, so prompts, reader and judge are byte-identical across arms. All paid callers use the
proxy. Monitor `/status`; stop owned processes if `halted` is true.

### Stage 2: full LongMemEval-S (500 questions)

Same commands without `--per-type 5`, once per arm and profile. Reuse (b) only if the identity check
passed. Skip the reader for questions whose (a) or (c) prompt is byte-identical to (b)'s and reuse
(b)'s answer. Those pairs are concordant by construction: count them and report them separately so
they do not dilute the discordant counts.

### Stage 3: BEAM 100K (gated, design only)

Existing flags: `--tier 100K --answerer-model gpt-5-mini --judge-model gpt-5.4-mini-2026-03-17
--top-k 100 --output-dir data/results/memory-tax/beam` on `runners/beam_judged_eval.py`. Arms (a)
and (c) need a new `--retrieval raw|automem|fused` switch over the same ≤500-character chunks *(new)*.
Confirm the pinned judge works through `judge_preflight` before spending.

## 8. Cost estimate

Token counts come from the local dataset: 500 questions, 23,867 sessions, 244.6M characters (about
61.2M tokens at 4 chars/token), mean session 10,251 characters. Prices are **not pinned**: the
`voyage-4` figure ($0.06/M input) is a third-party listing, the reader figures are the illustrative
ones in [paid-budget.md](../eval/paid-budget.md) ($0.25/M in, $2/M out), and the judge price is
unknown. Verify all of them into `prices.json` on the launch day; the proxy has no defaults.

| Component (full 500, per use) | Tokens | Estimate |
| --- | --- | --- |
| Embed haystack once (`voyage-4`) | 61.2M | about $3.7 |
| Reader input, top-10 sessions | about 12.9M | about $3.2 |
| Reader output (1-2k/q typical; 6k/q worst case) | 0.5-1.0M (3M cap) | $1.0-2.0 ($6 worst case) |
| Judge | about 0.5M in, 0.15M out | at most $2 |

| Stage | Contents | Estimate | Proposed cap |
| --- | --- | --- | --- |
| 0 | Tests, pins, census | $0 | none |
| 1 | 30 questions (6% of the totals above), 3 arms, 2 embeddings, 1-2 noise repeats of (a),(b) | about $2-3 | $4 |
| 2 lean | Reuse (b); (a) and (c) only; 2 embeddings, 2 readers, 2 judges | about $17-22 | $25 |
| 2 full | Rerun all three arms; 2 embeddings, 3 readers, 3 judges | about $21-29 | $30 |
| 3 BEAM | Per arm: about 1.7k LLM calls and 2M embedded tokens; from the 2026-06-16 run's call counts, not re-measured | about $1.5-3 each | decide at G3 |

Sanity anchor: the entire post-merge campaign (LME 500 plus two 30-question canaries plus LoCoMo
1,986 plus every retry) accounted **$9.81** of its $20 cap. The table is a conservative upper range
against that. Stage 2 for one profile likely exceeds the $10.19 left there, and "never raise a
campaign cap" applies: **each stage needs a new ledger and an explicit owner-approved cap.** The old
remainder is not an approval. P1 and P2 add enrichment/summarization LLM calls on top; price them at
the G1 review from the Stage 0 census rather than guessing here.

## 9. Threats to validity

- P0 is near-raw by construction; a null result there says little about production-style writes.
  P1/P2 carry the real question, so do not stop at P0.
- The paper's naive-RAG settings are unspecified and its code is unreleased, so (a) is ours.
- `gpt-5-mini` is an alias and can drift between baseline and new runs; the identity check and the
  per-call served-model record guard this.
- Reader and judge stochasticity can masquerade as tax; the noise floor and `reader_noise` tag
  bound it.
- Prefix-limited or non-stratified subsets are biased by dataset order; use `--per-type`.
- Raw datasets and run artifacts stay local per the `data/results` policy. Curated reports go in
  `docs/session_*.md` with the registry updated.

## 10. Follow-up slices

1. `runners/memory_tax/` raw backend, RRF fusion backend, `run_lme.py`, with unit tests.
2. `pair.py`: benefit/tax, McNemar, bootstrap, noise floor, with unit tests.
3. `diagnose.py`: cause probes and store-state census, with unit tests.
4. BEAM `--retrieval` switch.
5. After G1/G2: run reports under `docs/session_*.md`.
