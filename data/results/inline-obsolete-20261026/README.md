# Inline obsolete-memory relation comparison

This reruns the existing free 385-case ForgetEval adapter and its ten graph probes. These exploratory diagnostics are separate from official LoCoMo/LongMemEval claims.

`manifest.json` pins every server, adapter, upstream, runtime image and model. Bulk evidence and the complete paired input/verdict index are gitignored at `data/sweep_runs/inline-obsolete-20261026/`; its `FILES.sha256` is bound by the curated manifest. The full executed orchestration, commands, Compose configuration, health snapshots and cleanup logs are retained there.

The original external source paths are intentional frozen clean Git checkouts:

- Adapter root: `/Users/jgarturo/Projects/OpenAI/automem-evals/.worktrees/agent-kernel-worker-a5b095e4`, revision `4723034d2d5fe7a29f448ee4fed9d93e838c2724`.
- Lethe: the adapter root's `.agent-drafts/lethe`, revision `b6053b7bdacc78a91b9ea4bb25f32edad278c495`.
- Baseline: `/Users/jgarturo/Projects/OpenAI/automem.worktrees/baseline-candidate-20261022`, revision `3eaa1f5d4a622db8d85fa9e5f45519fbb67f8876`.
- Candidate: `/Users/jgarturo/Projects/OpenAI/automem.worktrees/inline-obsolete-relations`, revision `f5d88f14393f51ddbc6027ecabcf316090b8d445`.

The wrapper accepts replacement checkout paths explicitly and verifies the adapter file hash. The original adapter verifies the selected server revision/clean state and frozen Lethe revision before API access; only its server revision pin is overridden.

To replay, choose a fresh project/output per arm. Set `AUTOMEM_CHECKOUT`, `DIAG_ARM` and `DIAG_PORT` (18131 baseline, 18132 candidate), then use retained `compose.executed.yml` with `docker compose -p NEW_PROJECT -f PATH create`. Copy BGE cache from `pmb_92ebad9f_models:/source:ro` into `NEW_PROJECT_models:/target` with `cp -a /source/. /target/`, then `up -d`. The executed command ledger records the exact cache command and six original file hashes. Backends are FalkorDB v4.18.10/Qdrant v1.11.3; API source is read-only, BGE uses local 384d embeddings offline, enrichment/JIT/consolidation are stopped, and paid keys are empty.

After `/health` is healthy, run from the repository root with explicit paths:

```bash
python3.12 data/results/inline-obsolete-20261026/run_suite.py \
  --adapter ADAPTER_ROOT/scripts/benchmarks/forgeteval_automem.py \
  --upstream ADAPTER_ROOT/.agent-drafts/lethe --checkout SERVER_CHECKOUT \
  --revision FULL_SERVER_SHA --endpoint http://127.0.0.1:18131 \
  --graph forgeteval-postmerge-baseline --output NEW_RAW_OUTPUT
```

Use the candidate port/graph for its arm. Require all 385 case inputs equal and zero query errors before interpreting scores. Full graph scoring serializes every returned result row, including nested relations; top-k scoring checks only `row.memory.content`. Clean only the newly created project with its same Compose/environment via `down -v`. Do not access existing 8001/8780 stores. No model judge or paid embedding calls are used.
