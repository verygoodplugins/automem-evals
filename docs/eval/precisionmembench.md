# PrecisionMemBench — experimental retrieval-precision adapter

Track [issue #64](https://github.com/verygoodplugins/automem-evals/issues/64), independently of StateMemBench #50, MemTrace #51/#52, ForgetEval #31, FAMA #22/#23, MERIT #53, A-TMA #57, and DolphinBench #45. Related: #50 (current/superseded state), #31 (forgetting controls). Candidate: `opportunity:automem-graph-rag-research-scout`.

## Official artifacts, checked 2026-10-12

[Paper v4](https://arxiv.org/abs/2605.11325v4), revised 2026-07-29, CC BY 4.0; checked [HTML](https://arxiv.org/html/2605.11325v4) and [PDF](https://arxiv.org/pdf/2605.11325v4). Both identify Jeffrey Flynt and the benchmark repository. The [Tenure benchmark page](https://tenureai.dev/benchmark/) links the same release; [the author's personal site](https://jeffreyflynt.com/) appeared in search but direct access failed DNS resolution.

| Artifact | Immutable revision | License / contents |
| --- | --- | --- |
| [Official GitHub harness](https://github.com/tenurehq/precisionMemBench/tree/61a712a1754e7d27b6dee42da32a2c214b003ece) | `61a712a1754e7d27b6dee42da32a2c214b003ece` | MIT; 35 beliefs, 77 single-turn cases, two sessions containing 12 scored turns, executable assertions and report builder. |
| [Hugging Face release](https://huggingface.co/datasets/tenurehq/precisionmembench/tree/bf1a508a14fd38e4d316ff8932e8b9c4dea2a394) | `bf1a508a14fd38e4d316ff8932e8b9c4dea2a394` | MIT card; result/leaderboard tables, not the cases. |

Artifacts are public. Use the official cases; do not invent a substitute. The evaluation matrix in #64 rates source_quality 4/5, recency 4/5, automem_fit 5/5, reproducibility 4/5, leverage 4/5, effort 2/5 (effort measures cost). Small provider-authored fixtures and wrapper-supplied structure limit generalization.

## Mapping and reporting boundary

The protocol maps `/recall` UUIDs to belief IDs without expected-ID filtering. Exact, conjunctive per-run/user/scope tags gate recall; the upstream wrapper fans out multiple scopes and interleaves ranks. `current_only=true` suppresses inactive records. Explicit source replacements use old-to-new `INVALIDATED_BY` and persisted `t_invalid`, equivalent to the MCP `supersedes_memory_id` operation. Historical records remain stored. Resolved questions receive source `resolved_at` as `t_invalid`; alias updates patch the same UUID.

Use unchanged upstream assertions/report math. Upstream supplies persona, pinned facts, questions, and relation participants from its fixture index. Results therefore measure **AutoMem + the generic external wrapper**; structural passes do not prove native AutoMem context building. Preparation verifies all tracked upstream sources, permits only its exact idempotent patches, adds a provider config and awaits the upstream session alias-write promise (an ordering fix); no expectations or scoring formulas change. HTTP errors, indexing timeouts, or unknown UUIDs invalidate a run; inspect the trace before reporting.

Follow [maturation.md](maturation.md): cold uses indexed ingestion without enrichment/consolidation. Curated comparisons require a frozen shared matured profile, enrichment drain, narrative-clock maintenance, decay/forget off, and `timestamp <= as_of` guard; matured-full remains separate. This smoke has **maturation: cold; matured: blocked** pending narrative-clock maintenance. The official probes provide no explicit query as-of timestamp; do not invent one or call current wall-clock suppression a historical-time evaluation. No answerer or LLM judge is used, and no paper baseline is an AutoMem score.

## Reproduce the isolated smoke

Use a clean AutoMem checkout and Python 3.10+, Node 22+, Docker Compose. Use a fresh dedicated Compose project, or remove only that project's leftover benchmark volumes before retrying an interrupted run. The commands clear inherited `PRECISIONMEMBENCH_URL` so the upstream adapter uses the prepared loopback bridge. From this repo:

```sh
mkdir -p .agent-drafts
export AUTOMEM_SOURCE=/absolute/path/to/automem
# Build the local runtime image if absent:
docker build -t automem-flask-api "$AUTOMEM_SOURCE"
docker compose -p precisionmembench-smoke -f runners/precisionmembench/compose.yml up -d
git clone https://github.com/tenurehq/precisionMemBench .agent-drafts/precisionmembench-upstream
git -C .agent-drafts/precisionmembench-upstream checkout 61a712a1754e7d27b6dee42da32a2c214b003ece
(cd .agent-drafts/precisionmembench-upstream && npm ci --ignore-scripts --no-audit --no-fund)
python3 runners/precisionmembench/protocol.py --upstream .agent-drafts/precisionmembench-upstream \
  --endpoint http://127.0.0.1:8091 --isolated --trace .agent-drafts/precisionmembench-trace.jsonl
# In a second terminal, run sequentially; each RESEED resets only adapter-owned IDs:
(cd .agent-drafts/precisionmembench-upstream && env -u PRECISIONMEMBENCH_URL MEMORY_PROVIDER=automem RESEED=true \
  npm exec ava -- src/retrieval.external.eval.test.ts)
(cd .agent-drafts/precisionmembench-upstream && env -u PRECISIONMEMBENCH_URL MEMORY_PROVIDER=automem RESEED=true \
  npm exec ava -- src/session-retrieval.external.eval.test.ts)
# Stop the protocol with Ctrl-C to remove its memories, then stop the dedicated stack and its benchmark volumes:
docker compose -p precisionmembench-smoke -f runners/precisionmembench/compose.yml down -v
```

Failing benchmark assertions produce exit 1 and remain findings, not adapter-test failures. Protocol failures close the connection and terminate the bridge rather than returning a scoreable error body. Discard any partial report from such a run and inspect protocol trace errors separately. The protocol rejects external endpoints and redirects, binds loopback, and requires `--isolated`. Every add waits for graph/vector count agreement; indexing is ingestion, not maturation. Raw responses and official reports remain under `.agent-drafts/`; see [the committed smoke report](../../data/results/SUMMARY-20261012-precisionmembench.md) for observations and provenance. Next: freeze narrative-clock maturation before publishing a comparison; do not tune recall budgets to these gold cases.
