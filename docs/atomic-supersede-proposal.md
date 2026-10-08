# Proposal: atomic explicit supersession in AutoMem

Proposed for [verygoodplugins/automem](https://github.com/verygoodplugins/automem); this eval PR changes no AutoMem code. Motivation: [ForgetEval/#31](https://github.com/verygoodplugins/automem-evals/issues/31), evolving-state checks in [StateMemBench/#50](https://github.com/verygoodplugins/automem-evals/issues/50), and residual-leak checks motivated by [MemLeak](https://arxiv.org/abs/2606.29788).

## Observed partial states

[`graph-residual.json`](../data/results/forgeteval-adv/20261008/graph-residual.json) records deliberate interruptions of successful real HTTP calls against the isolated local stack. These are fault-injection observations, not spontaneous backend outages:

| Interruption | Observed durable state | Current recall |
| --- | --- | --- |
| After POST replacement, before PATCH source | Both records exist; source has no t_invalid; no INVALIDATED_BY call occurred. | OldCo and NewCo both returned. |
| After PATCH source, before POST association | Replacement exists; source has t_invalid; provenance edge was never written. | NewCo returned; audit linkage is missing. |

The first pair is `1c149f5e-3002-427b-92bd-5e29229d4cd0` → `e181be59-84e6-4f57-9886-1476a2ff1ea8`; the second is `43415707-15c2-48b7-974b-b8fce5d959f1` → `5eea8d56-f6b5-48f1-8f1c-c01e41e829c1`. Raw source/replacement GET responses, current recall, and the last completed stage are committed. Retrying the three calls after an ambiguous timeout can also create duplicate replacements; this is an inferred risk, not a third observed case.

## Proposed contract

`POST /memory/{source_id}/supersede` accepts replacement content plus normal store fields, an `expected_updated_at` source version, and a caller-generated idempotency key. The source ID is explicit; semantic target discovery stays with the caller.

```json
{"content":"Maya employer NewCo.","expected_updated_at":"<source version>","idempotency_key":"<unique request key>"}
```

One authoritative graph transaction must validate the source/version, create the replacement, set source `t_invalid` to the replacement's `t_valid`, create `source -[:INVALIDATED_BY]-> replacement`, and persist the idempotency receipt. Either all writes commit or none do. Return both IDs only after commit:

```json
{"source_memory_id":"<source>","replacement_memory_id":"<replacement>","t_invalid":"<commit time>","vector_sync":"pending"}
```

Missing source returns 404; stale version or conflicting reuse of the key returns 409 without a replacement. Identical retries return the original pair. Already-invalid sources require the original idempotency receipt or return 409. Keep source content/history for audit; release and hard purge remain separate operations.

FalkorDB and Qdrant cannot share this graph transaction. Persist a durable vector-update outbox atomically with the graph writes, then retry vector upserts/payload invalidation independently. `vector_sync` is explicit; a graph commit must never be described as an atomic cross-store commit. Current recall must consult authoritative lifecycle state while vectors lag and fail closed when that state cannot be validated.

## Required verification and limits

Inject failures before commit and at each graph-write boundary: neither a stray replacement nor an invalidated source without its edge may survive. Test lost responses/retries, competing source versions, unavailable Qdrant, restart/outbox replay, and old vectors returned before synchronization. Both IDs and the edge must agree after recovery.

Atomicity does not fix compound-fact loss (0/40 here), prefix target/width errors (23/39), or retained text that independently repeats deleted facts. It also does not fix the observed inline relation leak: all five supersede extension cases suppressed top-k source text but returned it under `relations[].memory.content`; all five purge cases passed. Apply current-state suppression to relation summaries and entity expansion separately, and test every returned surface. Full analysis: [ForgetEval-Adv report](eval/forgeteval-adv.md).
