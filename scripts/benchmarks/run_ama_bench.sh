#!/usr/bin/env bash
# Run AMA-Bench's open-ended QA split through the AutoMem BaseMethod adapter.
#
# This intentionally installs only AMA-Hub's API path dependencies: vLLM,
# torch, and the GPU-only baseline packages are not needed for --method automem.
# A live AutoMem endpoint and OPENAI_API_KEY are required for a judged run.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
METHOD="automem"
SMOKE=0
SMOKE_QUESTION_LIMIT="${AMA_BENCH_SMOKE_QUESTION_LIMIT:-25}"
AMA_HUB_DIR="${AMA_HUB_DIR:-$ROOT/third_party/AMA-Hub}"
AUTOMEM_ENDPOINT="${AUTOMEM_ENDPOINT:-http://localhost:8001}"
AUTOMEM_API_TOKEN="${AUTOMEM_API_TOKEN:-test-token}"
OUTPUT_DIR=""

usage() {
  cat <<'EOF'
Usage: bash scripts/benchmarks/run_ama_bench.sh --method automem [--smoke] [--output-dir DIR]

Runs AMA-Hub against dataset/test/open_end_qa_set.jsonl with OpenAI for both
answer generation and LLM-as-judge. --smoke deterministically limits the input
to 25 QA pairs by default (override AMA_BENCH_SMOKE_QUESTION_LIMIT).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --method) METHOD="$2"; shift 2 ;;
    --smoke) SMOKE=1; shift ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$METHOD" != "automem" ]]; then
  echo "This runner currently supports only --method automem." >&2
  exit 2
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required: AMA-Hub uses OpenAI for answers and LLM-as-judge." >&2
  exit 2
fi
if ! curl --fail --silent --show-error --max-time 5 \
  -H "X-Api-Key: $AUTOMEM_API_TOKEN" "$AUTOMEM_ENDPOINT/health" >/dev/null; then
  echo "AutoMem health check failed at $AUTOMEM_ENDPOINT. Start the local stack first." >&2
  exit 2
fi

if [[ ! -d "$AMA_HUB_DIR/.git" ]]; then
  mkdir -p "$(dirname "$AMA_HUB_DIR")"
  git clone https://github.com/AMA-Bench/AMA-Hub.git "$AMA_HUB_DIR"
fi

VENV="$AMA_HUB_DIR/.venv-automem-api"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet 'openai>=1.12.0' 'pyyaml>=6.0' 'tqdm>=4.65.0' 'numpy>=1.24.0'

DATASET_FILE="$AMA_HUB_DIR/dataset/test/open_end_qa_set.jsonl"
if [[ ! -s "$DATASET_FILE" ]]; then
  mkdir -p "$(dirname "$DATASET_FILE")"
  curl --fail --location --silent --show-error \
    'https://huggingface.co/datasets/AMA-bench/AMA-bench/resolve/main/test/open_end_qa_set.jsonl?download=true' \
    -o "$DATASET_FILE"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$ROOT/data/results/ama-bench/${timestamp}-${METHOD}$([[ "$SMOKE" == 1 ]] && printf '%s' '-smoke')"
fi
mkdir -p "$OUTPUT_DIR"

cp "$ROOT/scripts/benchmarks/ama_bench_adapter.py" "$AMA_HUB_DIR/src/method/automem.py"
AMA_HUB_DIR="$AMA_HUB_DIR" "$VENV/bin/python" - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["AMA_HUB_DIR"]) / "src/method_register.py"
source = path.read_text(encoding="utf-8")
needle = '    "claude_code": ("src.method.agent_method", "ClaudeCodeAgentMethod"),\n'
addition = needle + '    "automem": ("src.method.automem", "AutoMemMethod"),\n'
if '"automem": ("src.method.automem", "AutoMemMethod")' not in source:
    if needle not in source:
        raise SystemExit(f"Cannot find AMA-Hub registry insertion point in {path}")
    path.write_text(source.replace(needle, addition), encoding="utf-8")
PY

STATE_FILE="$OUTPUT_DIR/automem-state.json"
METHOD_CONFIG="$OUTPUT_DIR/automem-method-config.json"
cat >"$METHOD_CONFIG" <<EOF
{
  "endpoint": "$AUTOMEM_ENDPOINT",
  "token": "$AUTOMEM_API_TOKEN",
  "tag": "ama-bench-eval",
  "top_k": 8,
  "chunk_chars": 12000,
  "importance": 0.7,
  "state_file": "$STATE_FILE"
}
EOF

cleanup() {
  PYTHONPATH="$AMA_HUB_DIR" "$VENV/bin/python" "$AMA_HUB_DIR/src/method/automem.py" \
    --cleanup-state "$STATE_FILE" --endpoint "$AUTOMEM_ENDPOINT" --token "$AUTOMEM_API_TOKEN" || true
}
trap cleanup EXIT

TEST_FILE="$DATASET_FILE"
if [[ "$SMOKE" == 1 ]]; then
  TEST_FILE="$OUTPUT_DIR/open_end_qa_set.smoke.jsonl"
  DATASET_FILE="$DATASET_FILE" TEST_FILE="$TEST_FILE" LIMIT="$SMOKE_QUESTION_LIMIT" "$VENV/bin/python" - <<'PY'
import json
import os
from pathlib import Path

source = Path(os.environ["DATASET_FILE"])
target = Path(os.environ["TEST_FILE"])
limit = int(os.environ["LIMIT"])
remaining = limit
selected = []
for raw in source.read_text(encoding="utf-8").splitlines():
    if not raw or remaining <= 0:
        continue
    episode = json.loads(raw)
    pairs = episode.get("qa_pairs", [])[:remaining]
    if pairs:
        episode["qa_pairs"] = pairs
        selected.append(episode)
        remaining -= len(pairs)
if remaining == limit:
    raise SystemExit("Dataset did not contain any QA pairs")
target.write_text("".join(json.dumps(item) + "\n" for item in selected), encoding="utf-8")
print(f"Smoke subset: {limit - remaining} questions across {len(selected)} trajectories")
PY
fi

cd "$AMA_HUB_DIR"
"$VENV/bin/python" src/run.py \
  --llm-server api \
  --llm-config configs/openai_gpt5_mini.yaml \
  --judge-server api \
  --judge-config configs/llm_judge_gpt5_mini.yaml \
  --subset openend \
  --method automem \
  --method-config "$METHOD_CONFIG" \
  --test-file "$TEST_FILE" \
  --max-concurrency-episodes 1 \
  --max-concurrency-questions-per-episode 1 \
  --judge-max-concurrency 1 \
  --output-dir "$OUTPUT_DIR" \
  | tee "$OUTPUT_DIR/run.log"

result="$(find "$OUTPUT_DIR" -maxdepth 1 -name 'results_*.json' -print -quit)"
if [[ -z "$result" ]]; then
  echo "AMA-Hub did not produce an evaluation JSON in $OUTPUT_DIR" >&2
  exit 1
fi
cp "$result" "$OUTPUT_DIR/results.json"
echo "AMA-Bench result JSON: $OUTPUT_DIR/results.json"
