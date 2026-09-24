#!/usr/bin/env bash
# Run the exploratory AutoMem adapter for Memora/FAMA Track 2.
#
# Default: free protocol smoke over all weekly/software_engineer sessions.
# --full:  official Memora answer + multi-judge pass; intentionally requires
#          OPENAI_API_KEY and OPENROUTER_API_KEY before any data is ingested.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADAPTER="$ROOT/scripts/benchmarks/memora_fama_adapter.py"
MEMORA_DIR="${MEMORA_DIR:-$ROOT/third_party/memora}"
PERIOD="${MEMORA_PERIOD:-weekly}"
PERSONA="${MEMORA_PERSONA:-software_engineer}"
# Pin the released harness/data/evaluator revision so separate runs use the
# same Track 2 contract and are comparable. Override only for deliberate
# upstream-adapter compatibility work.
MEMORA_REF="${MEMORA_REF:-a6493188efc836d6511ed5e4163fe3ba87da30ff}"
MODE="smoke"

if [[ "${1:-}" == "--full" ]]; then
  MODE="full"
  shift
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--full]" >&2
  exit 2
fi

if [[ ! -d "$MEMORA_DIR/.git" ]]; then
  echo "[memora-fama] Fetching the public Memora harness into $MEMORA_DIR"
  git clone --depth 1 --no-checkout https://github.com/geniesinc/Memora.git "$MEMORA_DIR"
fi

if ! git -C "$MEMORA_DIR" cat-file -e "${MEMORA_REF}^{commit}" 2>/dev/null; then
  git -C "$MEMORA_DIR" fetch --depth 1 origin "$MEMORA_REF"
fi
git -C "$MEMORA_DIR" checkout --detach --quiet "$MEMORA_REF"
echo "[memora-fama] Memora revision: $(git -C "$MEMORA_DIR" rev-parse HEAD)"

if [[ "$MODE" == "smoke" ]]; then
  echo "[memora-fama] No-cost protocol smoke: $PERIOD/$PERSONA"
  python3 "$ADAPTER" --smoke --memora-dir "$MEMORA_DIR" --period "$PERIOD" --persona "$PERSONA"
  exit 0
fi

# The released Track 2 pipeline generates answers with OpenAI and scores each
# sub-question through OpenRouter judges.  It has no exact-match scoring mode.
missing=()
for variable in OPENAI_API_KEY OPENROUTER_API_KEY; do
  if [[ -z "${!variable:-}" ]]; then
    missing+=("$variable")
  fi
done
if (( ${#missing[@]} )); then
  echo "[memora-fama] Full FAMA scoring is blocked: missing ${missing[*]}." >&2
  echo "[memora-fama] The released harness has no rule-based/exact-match FAMA scorer." >&2
  echo "[memora-fama] Run without --full for the free protocol smoke." >&2
  exit 3
fi

RUN_TAG="${MEMORA_RUN_TAG:-memora-fama-$(date -u +%Y%m%dT%H%M%SZ)}"
COMMON=(--memora-dir "$MEMORA_DIR" --period "$PERIOD" --persona "$PERSONA"
        --endpoint "${AUTOMEM_ENDPOINT:-http://localhost:8001}"
        --token "${AUTOMEM_TOKEN:-test-token}" --run-tag "$RUN_TAG")

echo "[memora-fama] Track 2 ingestion: $PERIOD/$PERSONA (run tag: $RUN_TAG)"
python3 "$ADAPTER" "${COMMON[@]}" --ingest
echo "[memora-fama] Official Memora answer + strict multi-judge evaluation"
python3 "$ADAPTER" "${COMMON[@]}" --evaluate

REPORT_DIR="$MEMORA_DIR/data/$PERIOD/$PERSONA/eval_results/automem"
REPORT="$(find "$REPORT_DIR" -name 'eval_report_*.json' -type f -print | sort | tail -n 1)"
if [[ -z "$REPORT" ]]; then
  echo "[memora-fama] Evaluation finished without an eval_report JSON file." >&2
  exit 1
fi
python3 - "$REPORT" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    report = json.load(handle)
metrics = report.get("overall_metrics", {})
print("[memora-fama] FAMA: {:.2f} / 100".format(float(metrics.get("fama", 0.0))))
print("[memora-fama] Report:", sys.argv[1])
PY
