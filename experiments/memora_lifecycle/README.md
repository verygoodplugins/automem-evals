# Memora lifecycle diagnostic

This deterministic, local-only diagnostic exercises the actual Memora Track 2
adapter from PR #88 through the AutoMem HTTP API. It covers explicit-predecessor
rename, a second update, deletion and repeated deletion, reintroduction after
deletion, current and historical recall, inline related memories, exact user/run
scope, and two no-answer controls. It is a synthetic retrieval/lifecycle test;
it does **not** run Memora's answerer or judges and is **not a FAMA score**.

The runner archives the pinned AutoMem product revision into a temporary build
context and starts a uniquely named, internal-only Docker Compose project. It
publishes no ports, mounts no production volumes, disables enrichment and
background mutation workers, and removes only its own project and volumes. It
uses a cached local BGE-768 model and supplies embeddings on writes and queries;
it does not test the server's asynchronous embedding worker. `OPENAI_API_KEY`
and `VOYAGE_API_KEY` are blank in the container, the network is internal, and
model downloads are disabled. The runner requires Python 3.12+ and the locally
cached images `automem-flask-api:latest`, `falkordb/falkordb:latest`, and
`qdrant/qdrant:v1.11.3`. Exact image IDs, model hash, adapter hash, product SHA,
evaluation SHA, and experiment-source hashes are in the output. Image tags may
change; recorded IDs establish what was actually used.

The runner rejects existing output paths and refuses to run when its source or
adapter differs from the checked-out evaluation commit. Output contains only
synthetic labels, per-case outcomes, counts and audit metadata. No raw memories,
credentials or private traces are published. API failures and any matched error
log lines fail the run; lifecycle/precision failures are written to the output
and also cause a nonzero exit. The adapter's supersede operation spans multiple
HTTP calls and is not transactional; this suite does not simulate failures
between those calls and cannot establish rollback guarantees. Graph-unavailable
fallback behavior and agent answer quality are also outside this scope.

```sh
python3 -m unittest discover -s experiments/memora_lifecycle -p 'test_*.py' -v
/Users/jgarturo/Projects/OpenAI/automem/.venv/bin/python \
  experiments/memora_lifecycle/run.py \
  --product-repo /Users/jgarturo/Projects/OpenAI/automem \
  --model-cache /Users/jgarturo/.config/automem/models \
  --output /tmp/memora-lifecycle-new-result.json
```

The hard-coded product revision is the reviewed original-text candidate
`46481560b6bf8570a7a43fc1d7e2a5bfdae4e236`. The adapter dependency is
`a99366cd21a29c2d7aabaf600884f07c9d8e4f5e` (PR #88). Run from an evaluation
checkout that contains the committed experiment and this adapter revision.
A failed no-answer control means the server returned unrelated in-scope
memories, even if it correctly excluded deleted or out-of-scope evidence.
