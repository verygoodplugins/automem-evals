# Memora / FAMA — exploratory AutoMem adapter

This is an exploratory [Memora](https://github.com/geniesinc/Memora) Track 2
(memory-agent) integration. It is not an official AutoMem benchmark harness,
an official benchmark number, or a public leaderboard submission. The source
of truth for official benchmark claims remains the `automem` repository; see
[the repository boundary](../REPO_BOUNDARY.md).

Memora's released Track 2 contract is `BaseMemorySystem`: an adapter implements
`get_system_name`, `initialize_client`, `add_conversation_to_memory`,
`search_memories`, and `get_required_env_vars`. The public checkout currently
documents that contract in [`evals/README.md`](https://github.com/geniesinc/Memora/blob/main/evals/README.md)
and `evals/agent_eval/base_evaluator.py` (there is no separate
`evals/agent_eval/README.md` in the released revision).

## Design

[`scripts/benchmarks/memora_fama_adapter.py`](../../scripts/benchmarks/memora_fama_adapter.py)
implements that contract as `AutoMemFamaSystem`. It maps the released session
metadata rather than attempting to infer forgetting from prose:

| Memora operation | AutoMem action | FAMA consequence |
| --- | --- | --- |
| `add` | `store_memory` a session's `share_memory` turns, timestamped with the session date | Available to remembering, reasoning, and recommending retrieval. |
| `update` | `store_memory(..., supersedes_memory_id=<old>, supersede_relation="EVOLVED_INTO")` | The Python MCP-equivalent client writes the replacement, sets the old node's `t_invalid` to the historical update date, and creates old → new `EVOLVED_INTO`. |
| `delete` | Set the active fact's `t_invalid` to the deletion date; do not create a retrievable tombstone | A current-state query excludes the deleted value, directly exercising FAMA's forgetting-absence checks. |

The `AutoMemMCPClient` deliberately follows the MCP client's supersede behavior:
fetch old memory → store replacement → patch old `t_invalid` → associate old
to new. This matters because `supersedes_memory_id` is an MCP-tool feature,
not a raw `POST /memory` HTTP property. Updates use `EVOLVED_INTO` because the
benchmark labels them as fact evolution; a correction could instead use
`INVALIDATED_BY`.

For every question, `search_memories` calls `recall_memory` with all of the
run/user tags and `current_only: true`. Consequently, the answer-generation
model only sees current facts. This is useful across all three FAMA task types:
Remembering gets current direct facts, Reasoning gets current supporting facts,
and Recommending avoids recommending from superseded preferences. The judge's
`forgetting_absence` subquestions then penalize any stale fact that still leaks
into an answer.

## Run

The runner fetches the public Memora checkout to `third_party/memora` when it
is absent and checks out the pinned release revision
`a6493188efc836d6511ed5e4163fe3ba87da30ff`. That checkout is intentionally
ignored; it is an upstream input, not vendored source. Set `MEMORA_REF` only
for deliberate compatibility work against a different upstream revision.

```bash
# Free: reads every weekly/software_engineer session through the adapter,
# exercises writes/updates/deletions/current-only retrieval against an
# in-process protocol double, and prints lifecycle counts.
bash scripts/benchmarks/run_memora_fama.sh
```

The released harness has no rule-based or exact-match FAMA scorer. Its Track 2
pipeline calls OpenAI to answer questions and OpenRouter-backed LLM judges to
score the memory-presence and forgetting-absence subquestions. Therefore the
free smoke intentionally reports `fama: null` instead of manufacturing a
number.

```bash
# A real local AutoMem stack plus paid answer/judge credentials are required.
cd ../automem && docker compose up -d
cd ../automem-evals
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...
bash scripts/benchmarks/run_memora_fama.sh --full
```

`--full` fails before ingestion, with a clear message, if either key is absent.
It runs strict multi-judge evaluation and prints the generated local
`eval_report_*.json` FAMA score. For a full run, the script installs the
released evaluator's core dependencies (`openai`, `python-dotenv`, `tqdm`, and
`requests`) with `python3 -m pip`; it deliberately does not install optional
SDKs for the other memory-agent adapters. Use `MEMORA_PERIOD`, `MEMORA_PERSONA`,
`MEMORA_DIR`, `MEMORA_REF`, `AUTOMEM_ENDPOINT`, `AUTOMEM_TOKEN`, or `MEMORA_RUN_TAG` to
override the defaults. No command here submits results anywhere.

## Verification scope

The regression test verifies the two essential protocol properties: an update
passes `supersedes_memory_id`, invalidates the old node, and adds the correctly
directed lifecycle edge; retrieval includes `current_only: true`. The smoke
then runs those paths over the released weekly `software_engineer` data without
requiring a model provider.
