#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_AUTOMEM_DIR="$ROOT_DIR/../automem"
if [[ ! -d "$DEFAULT_AUTOMEM_DIR" && -d "$HOME/Projects/OpenAI/automem" ]]; then
  DEFAULT_AUTOMEM_DIR="$HOME/Projects/OpenAI/automem"
fi
AUTOMEM_DIR="${AUTOMEM_DIR:-"$DEFAULT_AUTOMEM_DIR"}"
AUTOMEM_PYTHON="${AUTOMEM_PYTHON:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BASELINE_AUTOMEM_DIR="${BASELINE_AUTOMEM_DIR:-"$AUTOMEM_DIR"}"
CANDIDATE_AUTOMEM_DIR="${CANDIDATE_AUTOMEM_DIR:-"$AUTOMEM_DIR"}"
BASELINE_AUTOMEM_PYTHON="${BASELINE_AUTOMEM_PYTHON:-}"
CANDIDATE_AUTOMEM_PYTHON="${CANDIDATE_AUTOMEM_PYTHON:-}"
AUTOMEM_RUNTIME_ENV_FILE="${AUTOMEM_RUNTIME_ENV_FILE:-"$CANDIDATE_AUTOMEM_DIR/.env"}"

SNAPSHOT=""
VARIANT="metadata-tags"
SKIP_RESTORE=false
WRITE_PROBES_ONLY=false
RESTORE_PLAN_ONLY=false
STRICT_PRESERVE_REVIEW=false
RUN_DIR=""
TOKEN="${AUTOMEM_EVAL_TOKEN:-${LOCAL_AUTOMEM_API_TOKEN:-test-token}}"

BASELINE_COMPOSE_PROJECT="${BASELINE_COMPOSE_PROJECT:-automem_metadata_baseline}"
CANDIDATE_COMPOSE_PROJECT="${CANDIDATE_COMPOSE_PROJECT:-automem_metadata_candidate}"
BASELINE_API_PORT="${BASELINE_API_PORT:-8011}"
BASELINE_QDRANT_PORT="${BASELINE_QDRANT_PORT:-6343}"
BASELINE_QDRANT_GRPC_PORT="${BASELINE_QDRANT_GRPC_PORT:-6345}"
BASELINE_FALKOR_PORT="${BASELINE_FALKOR_PORT:-6389}"
BASELINE_FALKOR_UI_PORT="${BASELINE_FALKOR_UI_PORT:-3010}"
CANDIDATE_API_PORT="${CANDIDATE_API_PORT:-8012}"
CANDIDATE_QDRANT_PORT="${CANDIDATE_QDRANT_PORT:-6344}"
CANDIDATE_QDRANT_GRPC_PORT="${CANDIDATE_QDRANT_GRPC_PORT:-6346}"
CANDIDATE_FALKOR_PORT="${CANDIDATE_FALKOR_PORT:-6390}"
CANDIDATE_FALKOR_UI_PORT="${CANDIDATE_FALKOR_UI_PORT:-3011}"

load_runtime_env_file() {
  local env_file="$1"
  if [[ -z "$env_file" || ! -f "$env_file" ]]; then
    return
  fi

  local exports
  exports="$("$PYTHON_BIN" - "$env_file" <<'PY'
import os
import shlex
import sys

safe_keys = {
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "VECTOR_SIZE",
    "VOYAGE_API_KEY",
    "VOYAGE_MODEL",
}
path = sys.argv[1]
try:
    lines = open(path, encoding="utf-8").read().splitlines()
except OSError:
    raise SystemExit(0)

for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    key = key.strip()
    if key.startswith("export "):
        key = key[len("export ") :].strip()
    if key not in safe_keys or os.environ.get(key):
        continue
    value = value.strip()
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
)"
  if [[ -n "$exports" ]]; then
    eval "$exports"
  fi
}

load_runtime_env_file "$AUTOMEM_RUNTIME_ENV_FILE"

usage() {
  printf '%s\n' "Usage:"
  printf '%s\n' "  bash scripts/real_data_metadata_eval.sh --snapshot SNAPSHOT [--variant metadata-tags|metadata-embedding|combined|server-metadata-search]"
  printf '\n%s\n' "Options:"
  printf '%s\n' "  --snapshot PATH             Restore-compatible AutoMem snapshot directory or .tar.gz."
  printf '%s\n' "  --variant VARIANT           metadata-tags, metadata-embedding, combined, or server-metadata-search. Default: metadata-tags."
  printf '%s\n' "  --skip-restore              Reuse already-running baseline/candidate local stacks."
  printf '%s\n' "  --write-probes-only         Generate metadata_probe_scenario.json + README and exit."
  printf '%s\n' "  --restore-plan-only         Generate probes and print restore commands without running Docker."
  printf '%s\n' "  --strict-preserve-review    Fail on preserve-suite review statuses, not only hard regressions."
  printf '%s\n' "  --run-dir PATH              Override output directory. Default: data/sweep_runs/<run-id>/."
  printf '%s\n' "  --token TOKEN               AutoMem API token. Default: test-token."
  printf '\n%s\n' "Environment:"
  printf '%s\n' "  BASELINE_COMPOSE_PROJECT / CANDIDATE_COMPOSE_PROJECT set isolated Docker project names."
  printf '%s\n' "  BASELINE_AUTOMEM_DIR / CANDIDATE_AUTOMEM_DIR set separate server source checkouts."
  printf '%s\n' "  BASELINE_AUTOMEM_PYTHON / CANDIDATE_AUTOMEM_PYTHON set per-checkout Python envs."
  printf '%s\n' "  AUTOMEM_RUNTIME_ENV_FILE loads shared embedding provider env vars for both stacks."
  printf '%s\n' "  BASELINE_*_PORT / CANDIDATE_*_PORT set isolated host ports, including QDRANT_GRPC_PORT."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot)
      SNAPSHOT="${2:-}"
      shift 2
      ;;
    --variant)
      VARIANT="${2:-}"
      shift 2
      ;;
    --skip-restore)
      SKIP_RESTORE=true
      shift
      ;;
    --write-probes-only)
      WRITE_PROBES_ONLY=true
      shift
      ;;
    --restore-plan-only)
      RESTORE_PLAN_ONLY=true
      shift
      ;;
    --strict-preserve-review)
      STRICT_PRESERVE_REVIEW=true
      shift
      ;;
    --run-dir)
      RUN_DIR="${2:-}"
      shift 2
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unexpected argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$SNAPSHOT" ]]; then
  echo "ERROR: --snapshot is required." >&2
  usage
  exit 2
fi

case "$VARIANT" in
  metadata-tags|metadata-embedding|combined|server-metadata-search) ;;
  *)
    echo "ERROR: invalid --variant: $VARIANT" >&2
    exit 2
    ;;
esac

RUN_LABEL="${METADATA_RUN_LABEL:-}"
if [[ -z "$RUN_LABEL" && "$VARIANT" == "server-metadata-search" ]]; then
  RUN_LABEL="metadata-sidecar-enabled"
fi
if [[ -z "$RUN_LABEL" ]]; then
  RUN_LABEL="$VARIANT"
fi

if [[ -z "$RUN_DIR" ]]; then
  RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-metadata-${VARIANT}"
  RUN_DIR="$ROOT_DIR/data/sweep_runs/$RUN_ID"
fi
mkdir -p "$RUN_DIR"
RUN_DIR="$(cd "$RUN_DIR" && pwd)"

resolve_automem_python() {
  local automem_dir="$1"
  local explicit_python="$2"
  if [[ -n "$explicit_python" ]]; then
    printf '%s\n' "$explicit_python"
  elif [[ -x "$automem_dir/.venv/bin/python" ]]; then
    printf '%s\n' "$automem_dir/.venv/bin/python"
  elif [[ -n "$AUTOMEM_PYTHON" ]]; then
    printf '%s\n' "$AUTOMEM_PYTHON"
  else
    printf '%s\n' "$PYTHON_BIN"
  fi
}

BASELINE_AUTOMEM_PYTHON="$(resolve_automem_python "$BASELINE_AUTOMEM_DIR" "$BASELINE_AUTOMEM_PYTHON")"
CANDIDATE_AUTOMEM_PYTHON="$(resolve_automem_python "$CANDIDATE_AUTOMEM_DIR" "$CANDIDATE_AUTOMEM_PYTHON")"
AUTOMEM_PYTHON="$CANDIDATE_AUTOMEM_PYTHON"

BASELINE_ENDPOINT="http://localhost:${BASELINE_API_PORT}"
CANDIDATE_ENDPOINT="http://localhost:${CANDIDATE_API_PORT}"

PROBE_SCENARIO="$RUN_DIR/metadata_probe_scenario.json"
METRICS_JSON="$RUN_DIR/metadata-ab-metrics.json"
REPORT_MD="$RUN_DIR/metadata-ab-report.md"
TRANSFORM_PLAN="$RUN_DIR/transform_plan.jsonl"
TRANSFORM_SUMMARY="$RUN_DIR/transform_summary.json"
VECTOR_PREFLIGHT="$RUN_DIR/vector_preflight.json"
PRESERVE_RUN_DIR="$RUN_DIR/preserve-suite"
PRESERVE_REPORT="$RUN_DIR/preserve-recall-cleanup-v1.md"

write_readme() {
  {
    printf '%s\n\n' "# Real-Data Metadata Eval Run"
    printf '%s\n' "- variant: \`$VARIANT\`"
    printf '%s\n' "- run label: \`$RUN_LABEL\`"
    printf '%s\n' "- snapshot: \`$SNAPSHOT\`"
    printf '%s\n' "- baseline automem dir: \`$BASELINE_AUTOMEM_DIR\`"
    printf '%s\n' "- candidate automem dir: \`$CANDIDATE_AUTOMEM_DIR\`"
    printf '%s\n' "- baseline automem python: \`$BASELINE_AUTOMEM_PYTHON\`"
    printf '%s\n' "- candidate automem python: \`$CANDIDATE_AUTOMEM_PYTHON\`"
    printf '%s\n' "- runtime env file: \`$AUTOMEM_RUNTIME_ENV_FILE\`"
    printf '%s\n' "- embedding provider: \`${EMBEDDING_PROVIDER:-}\`"
    printf '%s\n' "- vector size: \`${VECTOR_SIZE:-}\`"
    printf '%s\n' "- baseline compose project: \`$BASELINE_COMPOSE_PROJECT\`"
    printf '%s\n' "- candidate compose project: \`$CANDIDATE_COMPOSE_PROJECT\`"
    printf '%s\n' "- baseline endpoint: \`$BASELINE_ENDPOINT\`"
    printf '%s\n' "- candidate endpoint: \`$CANDIDATE_ENDPOINT\`"
    printf '%s\n' "- baseline qdrant grpc port: \`$BASELINE_QDRANT_GRPC_PORT\`"
    printf '%s\n' "- candidate qdrant grpc port: \`$CANDIDATE_QDRANT_GRPC_PORT\`"
    printf '%s\n' "- skip restore: \`$SKIP_RESTORE\`"
    printf '%s\n\n' "- probes only: \`$WRITE_PROBES_ONLY\`"
    printf '%s\n\n' "## Artifacts"
    printf '%s\n' "- \`metadata_probe_scenario.json\`"
    printf '%s\n' "- \`metadata-ab-report.md\`"
    printf '%s\n' "- \`metadata-ab-metrics.json\`"
    printf '%s\n' "- \`transform_plan.jsonl\`"
    printf '%s\n' "- \`transform_summary.json\`"
    printf '%s\n' "- \`vector_preflight.json\`"
    printf '%s\n' "- \`preserve-recall-cleanup-v1.md\`"
    printf '%s\n' "- \`raw/\`"
  } > "$RUN_DIR/README.md"
}

print_restore_plan() {
  printf '%s' "baseline restore: "
  printf '%q ' \
    bash \
    "$BASELINE_AUTOMEM_DIR/scripts/lab/clone_production.sh" \
    --restore-only "$SNAPSHOT" \
    --compose-project "$BASELINE_COMPOSE_PROJECT" \
    --api-port "$BASELINE_API_PORT" \
    --qdrant-port "$BASELINE_QDRANT_PORT" \
    --qdrant-grpc-port "$BASELINE_QDRANT_GRPC_PORT" \
    --falkordb-port "$BASELINE_FALKOR_PORT" \
    --falkordb-browser-port "$BASELINE_FALKOR_UI_PORT" \
    --python "$BASELINE_AUTOMEM_PYTHON"
  printf '\n'

  printf '%s' "candidate restore: "
  printf '%q ' \
    bash \
    "$CANDIDATE_AUTOMEM_DIR/scripts/lab/clone_production.sh" \
    --restore-only "$SNAPSHOT" \
    --compose-project "$CANDIDATE_COMPOSE_PROJECT" \
    --api-port "$CANDIDATE_API_PORT" \
    --qdrant-port "$CANDIDATE_QDRANT_PORT" \
    --qdrant-grpc-port "$CANDIDATE_QDRANT_GRPC_PORT" \
    --falkordb-port "$CANDIDATE_FALKOR_PORT" \
    --falkordb-browser-port "$CANDIDATE_FALKOR_UI_PORT" \
    --python "$CANDIDATE_AUTOMEM_PYTHON"
  printf '\n'
}

echo "[1/6] Generating metadata probes"
"$PYTHON_BIN" "$ROOT_DIR/runners/build_metadata_probe_scenario.py" \
  --snapshot "$SNAPSHOT" \
  --output "$PROBE_SCENARIO"
write_readme

if [[ "$RESTORE_PLAN_ONLY" == true ]]; then
  print_restore_plan
  echo "run dir: $RUN_DIR"
  exit 0
fi

if [[ "$WRITE_PROBES_ONLY" == true ]]; then
  echo "probes: $PROBE_SCENARIO"
  echo "run dir: $RUN_DIR"
  exit 0
fi

if [[ "$SKIP_RESTORE" == false ]]; then
  if [[ ! -f "$BASELINE_AUTOMEM_DIR/scripts/lab/clone_production.sh" ]]; then
    echo "ERROR: baseline AutoMem clone script not found at $BASELINE_AUTOMEM_DIR/scripts/lab/clone_production.sh" >&2
    exit 2
  fi
  if [[ ! -f "$CANDIDATE_AUTOMEM_DIR/scripts/lab/clone_production.sh" ]]; then
    echo "ERROR: candidate AutoMem clone script not found at $CANDIDATE_AUTOMEM_DIR/scripts/lab/clone_production.sh" >&2
    exit 2
  fi

  echo "[2/6] Restoring baseline stack"
  bash "$BASELINE_AUTOMEM_DIR/scripts/lab/clone_production.sh" \
    --restore-only "$SNAPSHOT" \
    --compose-project "$BASELINE_COMPOSE_PROJECT" \
    --api-port "$BASELINE_API_PORT" \
    --qdrant-port "$BASELINE_QDRANT_PORT" \
    --qdrant-grpc-port "$BASELINE_QDRANT_GRPC_PORT" \
    --falkordb-port "$BASELINE_FALKOR_PORT" \
    --falkordb-browser-port "$BASELINE_FALKOR_UI_PORT" \
    --python "$BASELINE_AUTOMEM_PYTHON"

  echo "[3/6] Restoring candidate stack"
  bash "$CANDIDATE_AUTOMEM_DIR/scripts/lab/clone_production.sh" \
    --restore-only "$SNAPSHOT" \
    --compose-project "$CANDIDATE_COMPOSE_PROJECT" \
    --api-port "$CANDIDATE_API_PORT" \
    --qdrant-port "$CANDIDATE_QDRANT_PORT" \
    --qdrant-grpc-port "$CANDIDATE_QDRANT_GRPC_PORT" \
    --falkordb-port "$CANDIDATE_FALKOR_PORT" \
    --falkordb-browser-port "$CANDIDATE_FALKOR_UI_PORT" \
    --python "$CANDIDATE_AUTOMEM_PYTHON"
else
  echo "[2/6] Skipping restore"
  echo "[3/6] Reusing candidate stack"
fi

if [[ "$VARIANT" == "server-metadata-search" ]]; then
  echo "[4/6] Checking baseline/candidate vector identity"
  "$CANDIDATE_AUTOMEM_PYTHON" "$ROOT_DIR/runners/check_vector_identity.py" \
    --variant "$VARIANT" \
    --baseline-qdrant-url "http://localhost:${BASELINE_QDRANT_PORT}" \
    --candidate-qdrant-url "http://localhost:${CANDIDATE_QDRANT_PORT}" \
    --baseline-qdrant-api-key "${LOCAL_QDRANT_API_KEY:-}" \
    --candidate-qdrant-api-key "${LOCAL_QDRANT_API_KEY:-}" \
    --plan-output "$TRANSFORM_PLAN" \
    --summary-output "$TRANSFORM_SUMMARY" \
    --vector-preflight-output "$VECTOR_PREFLIGHT"
else
  echo "[4/6] Applying candidate metadata treatment"
  FALKORDB_HOST=localhost \
  FALKORDB_PORT="$CANDIDATE_FALKOR_PORT" \
  FALKORDB_PASSWORD="${LOCAL_FALKORDB_PASSWORD:-}" \
  QDRANT_URL="http://localhost:${CANDIDATE_QDRANT_PORT}" \
  QDRANT_API_KEY="${LOCAL_QDRANT_API_KEY:-}" \
  "$CANDIDATE_AUTOMEM_PYTHON" "$ROOT_DIR/runners/apply_metadata_treatment.py" \
    --variant "$VARIANT" \
    --automem-dir "$CANDIDATE_AUTOMEM_DIR" \
    --plan-output "$TRANSFORM_PLAN" \
    --summary-output "$TRANSFORM_SUMMARY" \
    --vector-preflight-output "$VECTOR_PREFLIGHT"
fi

echo "[5/6] Running metadata A/B recall eval"
"$PYTHON_BIN" "$ROOT_DIR/runners/run_metadata_ab_eval.py" \
  --scenario "$PROBE_SCENARIO" \
  --baseline-endpoint "$BASELINE_ENDPOINT" \
  --candidate-endpoint "$CANDIDATE_ENDPOINT" \
  --token "$TOKEN" \
  --run-dir "$RUN_DIR" \
  --metrics-output "$METRICS_JSON" \
  --report "$REPORT_MD" \
  --run-label "$RUN_LABEL"

echo "[6/6] Running preserve/noise recall suite"
"$PYTHON_BIN" "$ROOT_DIR/runners/compare_recall_endpoints.py" \
  --scenario recall_cleanup_v1 \
  --baseline-endpoint "$BASELINE_ENDPOINT" \
  --candidate-endpoint "$CANDIDATE_ENDPOINT" \
  --token "$TOKEN" \
  --run-dir "$PRESERVE_RUN_DIR" \
  --report "$PRESERVE_REPORT" \
  --fail-on-preserve-regression

if [[ "$STRICT_PRESERVE_REVIEW" == true ]]; then
  "$PYTHON_BIN" - "$PRESERVE_RUN_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text())
bad = [
    row["id"]
    for row in summary.get("rows", [])
    if row.get("status") in {"REGRESSION", "review"}
]
if bad:
    print("strict preserve review failed: " + ", ".join(bad), file=sys.stderr)
    raise SystemExit(1)
PY
fi

echo "run dir: $RUN_DIR"
echo "metadata report: $REPORT_MD"
echo "preserve report: $PRESERVE_REPORT"
