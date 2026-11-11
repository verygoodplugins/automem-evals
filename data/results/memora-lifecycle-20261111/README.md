# Memora lifecycle diagnostic, 2026-11-11

A six-memory synthetic replay of the actual PR #88 adapter against isolated
AutoMem product revision `46481560b6bf8570a7a43fc1d7e2a5bfdae4e236`
passed **17 of 19** checks. It is a lifecycle/retrieval diagnostic, **not a
FAMA score** or an agent-answer benchmark. The vector-backed run supplied local
BGE-768 embeddings for writes and queries; all six graph and vector records
were present. There were 27 HTTP requests, no request failures, and no errors
in the API log audit. The disposable stack and its volumes were removed.

The explicit predecessor rename, second update, current-state old-version
exclusion, historical retrieval, inline old-payload filtering, deletion,
repeated deletion, update after deletion, and cross-scope exclusion passed.
Both abstention controls failed: the no-answer query and the wrong-scope query
each returned one unrelated in-scope result at `min_score=0`. Neither leaked an
obsolete/deleted or cross-scope fact. This small synthetic sample does not
measure population-level failure rates or judge response correctness.

`aggregate.json` contains the sanitized per-check outcomes and source, image,
model and adapter hashes. The exact harness commit was `f25fa6d`; see
[`experiments/memora_lifecycle/README.md`](../../../experiments/memora_lifecycle/README.md)
for reproduction and important limitations, including non-atomic update writes.
