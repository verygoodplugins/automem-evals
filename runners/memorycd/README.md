# MemoryCD AutoMem adapter (overlay)

**Draft.** Adds an `automem` memory-selection method to the upstream
[MemoryCD](https://github.com/AgentMemoryWorld/MemoryCD) harness, so AutoMem's
graph relations can be tested on cross-domain personalization. The only
evidence so far is a 4-user smoke, which does not support any conclusion.
Tracking: #30.

The files here are an overlay for a clean upstream clone. This repo does not
vendor the harness or its data.

| File | Purpose |
| --- | --- |
| `automem_method.py` | `AutoMemMethod`, a stdlib-only `BaseMethod` implementation that talks to AutoMem over HTTP |
| `apply_automem_method.py` | Copies the method into a MemoryCD clone and registers `--method automem` plus an optional `anthropic` LLM provider |
| `anthropic_compat.py` | Small OpenAI-chat-shaped wrapper around the Anthropic SDK, copied into the clone by the apply script |
| `create_subset.py` | Builds a deterministic small user subset from the released JSONL.gz |
| `test_automem_method.py` | Request-shape contract test against a stubbed harness and HTTP layer |

## What MemoryCD is

- Paper: [arXiv:2603.25973](https://arxiv.org/abs/2603.25973), Lifelong Agent workshop, ICLR 2026.
- Code: [AgentMemoryWorld/MemoryCD](https://github.com/AgentMemoryWorld/MemoryCD).
- Data: [WZDavid/MemoryCD](https://huggingface.co/datasets/WZDavid/MemoryCD) on Hugging Face.
- Real Amazon review histories across 12 domains. The released cross-domain
  JSONL and public harness ship 4 of them (`Beauty_and_Personal_Care`, `Books`,
  `Electronics`, `Home_and_Kitchen`), fixed in `eval_core.DOMAINS`.
- Two settings: **single-domain** (memory and test from one domain) and
  **cross-domain** (memory from other domains, test on a target domain).
- Four tasks: `rating_prediction`, `review_summarization`, `review_generation`,
  `item_ranking`.
- The paper's baselines (Mem0, A-Mem, MemoryBank, ReadAgent, long-context, BM25
  RAG) fall short across 14 LLMs.

Why it matters for AutoMem: our other benchmark adapters (BEAM, Memora/FAMA,
Mem2ActBench, AMemGym) are dialogue-centric with one domain of discourse.
MemoryCD's cross-domain setting needs memory formed in one domain (a `Books`
review) to inform a prediction in another (`Electronics`). That is the shape of
AutoMem's `RELATES_TO` / `PART_OF` edges, and lexical or recency baselines
handle it badly.

## How the adapter works

MemoryCD's plug-in point is `methods/base_method.py`
(`select_memory(memory, target_item, task)`). `eval_core.build_method()`
dispatches to `long_context` (recency window) or `rag` (BM25 top-K); the
overlay adds an `automem` branch.

1. **Ingest** (once per user and history fingerprint, in process): each
   interaction is written with `POST /memory` as a `Preference` memory. Tags
   are `memorycd`, a random per-run tag (`memorycd-eval-<hex>`), a hashed user
   tag and `memorycd-domain-<domain>`. `parent_asin` goes in metadata.
2. **Cross-domain linking:** one synthetic domain-profile memory per
   `(user, domain)`. Each interaction gets a `PART_OF` edge to its profile, and
   the profiles get pairwise `RELATES_TO` edges, both batched through
   `POST /associate`. Edges are explicit and deterministic; no LLM infers them.
3. **Recall** (per target item): `GET /recall` with the run and user tags,
   `tag_mode=all`, `expand_relations=true`, `relation_limit=20` and the
   benchmark's memory cap. Result IDs map back to the exact MemoryCD
   interaction objects the prompt builder expects.
4. **All four tasks** share this path. `select_memory` returns the same shape
   for every task; only the prompt differs, as with `long_context` and `rag`.

On an AutoMem HTTP failure the method records `last_error`, prints
`Warning: AutoMem ... using recency fallback` to stderr, and returns the
recency window. The run keeps going, but that prediction is no longer
graph-backed, so check stderr before trusting an `automem` row.

## Setup

Keep the upstream clone outside this repo.

```bash
git clone --depth 1 https://github.com/AgentMemoryWorld/MemoryCD.git "$MEMORYCD"
python3 -m venv "$MEMORYCD/.venv"
"$MEMORYCD/.venv/bin/pip" install -r "$MEMORYCD/requirements.txt"
"$MEMORYCD/.venv/bin/pip" install 'anthropic>=0.40'   # only for LLM_PROVIDER=anthropic

python3 runners/memorycd/apply_automem_method.py "$MEMORYCD"
```

The apply script is idempotent and fails loudly if an expected upstream line
has moved. `anthropic` is installed in the MemoryCD venv, never in this repo.

Data: the full release is a multi-GB Hugging Face download. The smoke below
used only `users/cross_domain_users_sampled.jsonl.gz` (about 108 MB):

```bash
curl -L --fail -o "$MEMORYCD_CACHE/cross_domain_users_sampled.jsonl.gz" \
  'https://huggingface.co/datasets/WZDavid/MemoryCD/resolve/main/users/cross_domain_users_sampled.jsonl.gz?download=true'
python3 runners/memorycd/create_subset.py \
  --input "$MEMORYCD_CACHE/cross_domain_users_sampled.jsonl.gz" \
  --output "$MEMORYCD/data/memorycd_books_electronics_4users.jsonl" \
  --manifest "$MEMORYCD/data/memorycd_books_electronics_4users.manifest.json"
```

`create_subset.py` takes the first `--users` users with at least
`--num-test + 1` target-domain and one source-domain interaction. It keeps the
held-out tail plus the `--max-memory-per-domain` most recent interactions per
domain.

## Environment

| Variable | Purpose |
| --- | --- |
| `AUTOMEM_API_URL` | AutoMem base URL. Default `http://localhost:8001` (the local stack) |
| `AUTOMEM_API_TOKEN` or `AUTOMEM_API_KEY` | AutoMem token, sent as `Authorization: Bearer` and `X-API-Key`. `AUTOMEM_API_TOKEN` wins if both are set |
| `LLM_PROVIDER` | Upstream `openai` or `openrouter`; the overlay adds `anthropic` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` | Key for the chosen provider |

## Run

From the MemoryCD clone, one row of the smoke table. Swap `rag` for `automem`,
or use `evaluation_all_4task.py --domain Books` for the single-domain rows.

```bash
cd "$MEMORYCD"
AUTOMEM_API_URL=http://localhost:8001 AUTOMEM_API_KEY=test-token \
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... \
.venv/bin/python evaluation_all_4task_cross_domain.py --task rating_prediction \
  --target-domain Books --source-domains Electronics \
  --input data/memorycd_books_electronics_4users.jsonl --meta-dir meta-empty \
  --method automem --llm-model claude-sonnet-4-6 --num-test 1 \
  --max-users 4 --max-memory-items 4 --log-dir logs/cross-automem-k4
```

## Smoke result (2026-09-13): 4 users, not statistically meaningful

Setup: the first four users with `Books >= 2` and `Electronics >= 1`, the eight
most recent pre-test interactions per domain, one held-out `Books` rating per
user, no item-metadata download (`--meta-dir meta-empty`). The available
OpenAI key was out of credit, so predictions used `claude-sonnet-4-6` through
the overlay's Anthropic wrapper at provider-default sampling. There were no
synthetic examples, no fallback predictions and no AutoMem warnings.

| Setting | Method | Users / predictions | K | MAE | RMSE |
|---|---|---:|---:|---:|---:|
| Cross: Books target, Electronics memory | RAG/BM25 | 4 / 4 | 4 | 0.5000 | 0.7071 |
| Cross: Books target, Electronics memory | AutoMem graph recall | 4 / 4 | 4 | 0.5000 | 0.7071 |
| Single: Books | RAG/BM25 | 4 / 4 | 4 | 0.2500 | 0.5000 |
| Single: Books | AutoMem graph recall | 4 / 4 | 4 | 0.5000 | 0.7071 |

**Assessment:** this does **not** show that graph relation linking helps
cross-domain personalization. AutoMem tied BM25 in the one cross-domain cell
and was worse in the single-domain check. Four users with one rating each is
far too small to conclude anything. It shows only that the pipeline runs end
to end.

Before that, a one-user adapter probe against a live AutoMem ingested eight
real `Electronics` interactions, created the domain node and edges, and
completed relation-expanded recall with no fallback: `POST /memory=9`,
`POST /associate=1`, `GET /recall=1`, `selected=8`, `last_error=null`. The
probe's memories were deleted afterwards.

## Known limitations

- **No cleanup.** The method never deletes what it ingests. Use a disposable
  AutoMem stack, or delete the run's memories afterwards; every write carries
  the `memorycd` tag.
- **`user_id` plumbing is unverified.** The method takes an optional `user_id`
  keyword, and the overlay does not patch the harness to pass one. If the
  upstream caller omits it, every user in a run shares the `anonymous` user
  tag. Recall then competes across users: other users' results are dropped
  after recall but still use up `limit` slots, which can push selection toward
  the recency fallback. Check this before a larger run.
- **The Anthropic wrapper caps output at `max_tokens=16`** and ignores other
  sampling arguments. That fits `rating_prediction` only. The generation and
  summarization tasks need a larger cap.
- The ingest-once cache lives in process memory, so each script invocation
  re-ingests.

## Next

- Run a statistically meaningful subset (100+ users per setting) on rating
  prediction, then the other three tasks, with a fixed-temperature or
  multi-seed protocol and item metadata.
- Compare plain recall with `expand_relations` to isolate relation linking.
- Decide go/no-go on a full cross-domain run.

## Verification

```bash
python3 runners/memorycd/test_automem_method.py
```

This covers ingest, `PART_OF` and `RELATES_TO` association batches,
relation-expanded recall, and mapping recall IDs back to interactions. It runs
against a stub `BaseMethod` in a temp dir with a patched `urlopen`, so it needs
neither an upstream clone nor AutoMem.
