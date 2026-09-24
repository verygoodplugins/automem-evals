# Experiment log

## AMA-Bench AutoMem adapter — 2026-09-24

- Added a GPU-free AMA-Hub adapter that stores trajectory chunks through
  AutoMem `POST /memory` and retrieves tagged context through `GET /recall`.
- Isolation: every record gets the dedicated `ama-bench-eval` tag; the adapter
  deletes tracked IDs before the next trajectory and the runner cleans the last
  trajectory in an EXIT trap. It never enumerates or deletes unrelated memory.
- Intended judged smoke command (25 deterministic open-ended QA pairs):

  ```bash
  OPENAI_API_KEY=... bash scripts/benchmarks/run_ama_bench.sh --method automem --smoke
  ```

- Result status: **no judged accuracy available**. The local Docker AutoMem
  stack was started and the adapter passed a live protocol check: one tagged
  record was stored, retrieved through `/recall`, deleted, and confirmed absent
  in a follow-up tag-gated recall. A 25-question/3-trajectory smoke attempted
  real construction (the first trajectory produced nine stored chunks), but its
  first OpenAI answer request stalled. After cleanup, a direct minimal OpenAI
  probe returned `429 credit_balance_exhausted`; there are no API credits for
  either answer generation or the LLM judge. Thus no score is claimed. A real
  judged smoke needs OpenAI API credits; a full run additionally needs enough
  time and budget for the complete test split. Do not submit any result to the
  public AMA-Bench leaderboard without owner approval.
- Comparison target once a score exists: the current
  [AMA-Bench leaderboard](https://huggingface.co/spaces/AMA-bench/AMA-bench-Leaderboard/blob/main/data/agent.jsonl)
  lists verified Qwen3-32B Long context and HippoRAG2 results. Applying the
  Space's published `qa_distribution.json` weighting gives 51.35% and 44.05%
  average accuracy respectively (Space commit `da059ea`); these are reference
  baselines only, not comparison claims for the unrun adapter.
