#!/usr/bin/env bash
# Run a local-only real-data entity tag repair evaluation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVALS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/real_data_entity_repair_eval.sh"

AUTOMEM_REPO="${AUTOMEM_REPO:-$EVALS_ROOT/../automem}"
SNAPSHOT=""
RUN_ID="$(date -u +%Y%m%d-%H%M%S)-real-data-entity-repair"
TOKEN="${AUTOMEM_API_TOKEN:-test-token}"
ADMIN_TOKEN="${ADMIN_API_TOKEN:-test-admin-token}"
SCENARIO="recall_cleanup_v1"
BATCH_SIZE="${BATCH_SIZE:-250}"
GRAPH_UPDATE_TIMEOUT_SECONDS="${GRAPH_UPDATE_TIMEOUT_SECONDS:-60}"
QDRANT_READY_TIMEOUT_SECONDS="${QDRANT_READY_TIMEOUT_SECONDS:-180}"
QDRANT_READY_RETRY_DELAY_SECONDS="${QDRANT_READY_RETRY_DELAY_SECONDS:-3}"
API_READY_TIMEOUT_SECONDS="${API_READY_TIMEOUT_SECONDS:-180}"
REPAIR_MODE="${REPAIR_MODE:-canonicalize-safe}"
AUDIT_TIMEOUT_SECONDS="${AUDIT_TIMEOUT_SECONDS:-30}"
WRITE_PROBES_ONLY=false
SKIP_RESTORE=false
SKIP_ENTITY_AUDIT=false
SKIP_VECTOR_PREFLIGHT=false
SKIP_VECTOR_IDENTITY=false
SYNC_BASELINE_FIRST=false
RUN_ENTITY_MIGRATION=false
STAGED_LOOP=false
PRINT_STAGED_LOOP=false
FULL_ENTITY_AUDIT=false
STRICT_PRESERVE_REVIEW=false
CLEANUP_EXISTING_LAB_STACKS=false
LOCAL_API_PIDS=()

BASELINE_COMPOSE_PROJECT="${BASELINE_COMPOSE_PROJECT:-automem-real-baseline}"
CANDIDATE_COMPOSE_PROJECT="${CANDIDATE_COMPOSE_PROJECT:-automem-real-clean}"
BASELINE_API_PORT="${BASELINE_API_PORT:-8011}"
BASELINE_QDRANT_PORT="${BASELINE_QDRANT_PORT:-6343}"
BASELINE_QDRANT_GRPC_PORT="${BASELINE_QDRANT_GRPC_PORT:-6345}"
BASELINE_FALKORDB_PORT="${BASELINE_FALKORDB_PORT:-6389}"
BASELINE_BROWSER_PORT="${BASELINE_BROWSER_PORT:-3011}"
CANDIDATE_API_PORT="${CANDIDATE_API_PORT:-8012}"
CANDIDATE_QDRANT_PORT="${CANDIDATE_QDRANT_PORT:-6344}"
CANDIDATE_QDRANT_GRPC_PORT="${CANDIDATE_QDRANT_GRPC_PORT:-6346}"
CANDIDATE_FALKORDB_PORT="${CANDIDATE_FALKORDB_PORT:-6390}"
CANDIDATE_BROWSER_PORT="${CANDIDATE_BROWSER_PORT:-3012}"
BASELINE_ENDPOINT=""
CANDIDATE_ENDPOINT=""
BASELINE_QDRANT_URL=""
CANDIDATE_QDRANT_URL=""
QDRANT_COLLECTION="${QDRANT_COLLECTION:-memories}"
BASELINE_ENDPOINT_PROVIDED=false
CANDIDATE_ENDPOINT_PROVIDED=false
BASELINE_QDRANT_URL_PROVIDED=false
CANDIDATE_QDRANT_URL_PROVIDED=false
BASELINE_API_PORT_PROVIDED=false
CANDIDATE_API_PORT_PROVIDED=false
BASELINE_QDRANT_PORT_PROVIDED=false
CANDIDATE_QDRANT_PORT_PROVIDED=false

usage() {
    printf '%s\n' \
        "Usage:" \
        "  $0 --snapshot NAME_OR_PATH [options]" \
        "  $0 --write-probes-only [options]" \
        "" \
        "Restores one production snapshot into two isolated local AutoMem stacks, repairs" \
        "entity tags on the candidate stack only, and compares recall before/after." \
        "" \
        "Options:" \
        "  --snapshot NAME_OR_PATH       Snapshot name/path accepted by automem/scripts/lab/clone_production.sh --restore-only." \
        "  --automem-repo PATH           Sibling automem repo. Default: $AUTOMEM_REPO" \
        "  --run-id ID                   Run directory name under data/sweep_runs/." \
        "  --scenario NAME_OR_PATH       Base scenario to copy into the run dir. Default: $SCENARIO" \
        "  --token TOKEN                 Local AutoMem API token. Default: $TOKEN" \
        "  --admin-token TOKEN           Local AutoMem admin token. Default: $ADMIN_TOKEN" \
        "  --baseline-endpoint URL       Baseline API endpoint. Default: http://localhost:$BASELINE_API_PORT" \
        "  --candidate-endpoint URL      Candidate API endpoint. Default: http://localhost:$CANDIDATE_API_PORT" \
        "  --baseline-api-port PORT      Baseline API host port. Default: $BASELINE_API_PORT" \
        "  --candidate-api-port PORT     Candidate API host port. Default: $CANDIDATE_API_PORT" \
        "  --repair-mode MODE            Repair mode passed to repair_entity_tags.py: sync-only, reject-only, or canonicalize-safe. Default: $REPAIR_MODE" \
        "  --skip-entity-audit           Skip /entities/audit captures for large/noisy local clones." \
        "  --audit-timeout-seconds N     Max seconds for each /entities/audit request. Default: $AUDIT_TIMEOUT_SECONDS" \
        "  --graph-update-timeout-seconds N" \
        "                                Max seconds for each FalkorDB repair write batch. Default: $GRAPH_UPDATE_TIMEOUT_SECONDS" \
        "  --qdrant-ready-timeout-seconds N" \
        "                                Max seconds to wait for each local Qdrant endpoint before vector checks. Default: $QDRANT_READY_TIMEOUT_SECONDS" \
        "  --skip-vector-preflight       Skip recall warm-up vector readiness checks." \
        "  --skip-vector-identity        Skip baseline/candidate Qdrant vector identity checks." \
        "  --sync-baseline-first         Run sync-only on the baseline before candidate repair." \
        "                                Enabled automatically for non-sync-only modes." \
        "  --full-entity-audit           Capture full /entities/audit arrays instead of summary mode." \
        "  --baseline-qdrant-url URL     Baseline Qdrant URL. Default: http://localhost:$BASELINE_QDRANT_PORT" \
        "  --candidate-qdrant-url URL    Candidate Qdrant URL. Default: http://localhost:$CANDIDATE_QDRANT_PORT" \
        "  --baseline-qdrant-port PORT   Baseline Qdrant REST host port. Default: $BASELINE_QDRANT_PORT" \
        "  --candidate-qdrant-port PORT  Candidate Qdrant REST host port. Default: $CANDIDATE_QDRANT_PORT" \
        "  --baseline-qdrant-grpc-port PORT" \
        "                                Baseline Qdrant gRPC host port for restore. Default: $BASELINE_QDRANT_GRPC_PORT" \
        "  --candidate-qdrant-grpc-port PORT" \
        "                                Candidate Qdrant gRPC host port for restore. Default: $CANDIDATE_QDRANT_GRPC_PORT" \
        "  --baseline-falkordb-port PORT Baseline FalkorDB host port. Default: $BASELINE_FALKORDB_PORT" \
        "  --candidate-falkordb-port PORT" \
        "                                Candidate FalkorDB host port. Default: $CANDIDATE_FALKORDB_PORT" \
        "  --baseline-browser-port PORT  Baseline FalkorDB browser host port. Default: $BASELINE_BROWSER_PORT" \
        "  --candidate-browser-port PORT Candidate FalkorDB browser host port. Default: $CANDIDATE_BROWSER_PORT" \
        "  --run-entity-migration        After the pre-migration recall comparison passes, run Entity migration and a second comparison." \
        "  --strict-preserve-review      Fail recall comparison on preserve review churn, not only hard regressions." \
        "  --cleanup-existing-lab-stacks Stop stale local lab Docker compose projects before restore." \
        "  --staged-loop                 Run sync-only, reject-only, canonicalize-safe, then post-migration." \
        "  --print-staged-loop           Print staged-loop commands and exit without running them." \
        "  --write-probes-only           Only write the local ignored probe scenario and exit." \
        "  --skip-restore                Use already-running local baseline/candidate endpoints." \
        "  --help                        Show this help."
}

is_local_endpoint() {
    python3 -c '
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
host = (parsed.hostname or "").lower()
if parsed.scheme in {"http", "https"} and host in {"localhost", "127.0.0.1", "::1"}:
    raise SystemExit(0)
raise SystemExit(1)
' "$1"
}

require_local_endpoint() {
    local label="$1"
    local endpoint="$2"
    if ! is_local_endpoint "$endpoint"; then
        echo "ERROR: refusing non-local $label endpoint without an explicit local clone: $endpoint" >&2
        exit 2
    fi
}

url_port() {
    python3 -c '
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
if parsed.port is not None:
    print(parsed.port)
elif parsed.scheme == "https":
    print(443)
else:
    print(80)
' "$1"
}

cleanup_local_apis() {
    local pid
    for pid in "${LOCAL_API_PIDS[@]}"; do
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup_local_apis EXIT

cleanup_existing_lab_stacks() {
    local project
    while IFS= read -r project; do
        if [ -z "$project" ]; then
            continue
        fi
        case "$project" in
            automem-real-*|automem-loop-*|automem-strict-*|automem-fresh-*|automem-snapshot-download)
                echo "cleanup_lab_stack: $project"
                docker compose -p "$project" down -v --remove-orphans || true
                ;;
        esac
    done < <(
        docker ps -a \
            --filter "label=com.docker.compose.project" \
            --format '{{.Label "com.docker.compose.project"}}' | sort -u
    )
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --snapshot)
            SNAPSHOT="${2:-}"
            shift 2
            ;;
        --automem-repo)
            AUTOMEM_REPO="${2:-}"
            shift 2
            ;;
        --run-id)
            RUN_ID="${2:-}"
            shift 2
            ;;
        --scenario)
            SCENARIO="${2:-}"
            shift 2
            ;;
        --token)
            TOKEN="${2:-}"
            shift 2
            ;;
        --admin-token)
            ADMIN_TOKEN="${2:-}"
            shift 2
            ;;
        --baseline-endpoint)
            BASELINE_ENDPOINT="${2:-}"
            BASELINE_ENDPOINT_PROVIDED=true
            shift 2
            ;;
        --candidate-endpoint)
            CANDIDATE_ENDPOINT="${2:-}"
            CANDIDATE_ENDPOINT_PROVIDED=true
            shift 2
            ;;
        --baseline-api-port)
            BASELINE_API_PORT="${2:-}"
            BASELINE_API_PORT_PROVIDED=true
            shift 2
            ;;
        --candidate-api-port)
            CANDIDATE_API_PORT="${2:-}"
            CANDIDATE_API_PORT_PROVIDED=true
            shift 2
            ;;
        --baseline-qdrant-url)
            BASELINE_QDRANT_URL="${2:-}"
            BASELINE_QDRANT_URL_PROVIDED=true
            shift 2
            ;;
        --candidate-qdrant-url)
            CANDIDATE_QDRANT_URL="${2:-}"
            CANDIDATE_QDRANT_URL_PROVIDED=true
            shift 2
            ;;
        --baseline-qdrant-port)
            BASELINE_QDRANT_PORT="${2:-}"
            BASELINE_QDRANT_PORT_PROVIDED=true
            shift 2
            ;;
        --candidate-qdrant-port)
            CANDIDATE_QDRANT_PORT="${2:-}"
            CANDIDATE_QDRANT_PORT_PROVIDED=true
            shift 2
            ;;
        --baseline-qdrant-grpc-port)
            BASELINE_QDRANT_GRPC_PORT="${2:-}"
            shift 2
            ;;
        --candidate-qdrant-grpc-port)
            CANDIDATE_QDRANT_GRPC_PORT="${2:-}"
            shift 2
            ;;
        --baseline-falkordb-port)
            BASELINE_FALKORDB_PORT="${2:-}"
            shift 2
            ;;
        --candidate-falkordb-port)
            CANDIDATE_FALKORDB_PORT="${2:-}"
            shift 2
            ;;
        --baseline-browser-port)
            BASELINE_BROWSER_PORT="${2:-}"
            shift 2
            ;;
        --candidate-browser-port)
            CANDIDATE_BROWSER_PORT="${2:-}"
            shift 2
            ;;
        --repair-mode)
            REPAIR_MODE="${2:-}"
            shift 2
            ;;
        --skip-entity-audit)
            SKIP_ENTITY_AUDIT=true
            shift
            ;;
        --audit-timeout-seconds)
            AUDIT_TIMEOUT_SECONDS="${2:-}"
            shift 2
            ;;
        --graph-update-timeout-seconds)
            GRAPH_UPDATE_TIMEOUT_SECONDS="${2:-}"
            shift 2
            ;;
        --qdrant-ready-timeout-seconds)
            QDRANT_READY_TIMEOUT_SECONDS="${2:-}"
            shift 2
            ;;
        --skip-vector-preflight)
            SKIP_VECTOR_PREFLIGHT=true
            shift
            ;;
        --skip-vector-identity)
            SKIP_VECTOR_IDENTITY=true
            shift
            ;;
        --sync-baseline-first)
            SYNC_BASELINE_FIRST=true
            shift
            ;;
        --full-entity-audit)
            FULL_ENTITY_AUDIT=true
            shift
            ;;
        --run-entity-migration)
            RUN_ENTITY_MIGRATION=true
            shift
            ;;
        --strict-preserve-review)
            STRICT_PRESERVE_REVIEW=true
            shift
            ;;
        --cleanup-existing-lab-stacks)
            CLEANUP_EXISTING_LAB_STACKS=true
            shift
            ;;
        --staged-loop)
            STAGED_LOOP=true
            shift
            ;;
        --print-staged-loop)
            PRINT_STAGED_LOOP=true
            shift
            ;;
        --write-probes-only)
            WRITE_PROBES_ONLY=true
            shift
            ;;
        --skip-restore)
            SKIP_RESTORE=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unexpected argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ "$BASELINE_ENDPOINT_PROVIDED" = true ] && [ "$BASELINE_API_PORT_PROVIDED" = false ]; then
    BASELINE_API_PORT="$(url_port "$BASELINE_ENDPOINT")"
fi
if [ "$CANDIDATE_ENDPOINT_PROVIDED" = true ] && [ "$CANDIDATE_API_PORT_PROVIDED" = false ]; then
    CANDIDATE_API_PORT="$(url_port "$CANDIDATE_ENDPOINT")"
fi
if [ "$BASELINE_QDRANT_URL_PROVIDED" = true ] && [ "$BASELINE_QDRANT_PORT_PROVIDED" = false ]; then
    BASELINE_QDRANT_PORT="$(url_port "$BASELINE_QDRANT_URL")"
fi
if [ "$CANDIDATE_QDRANT_URL_PROVIDED" = true ] && [ "$CANDIDATE_QDRANT_PORT_PROVIDED" = false ]; then
    CANDIDATE_QDRANT_PORT="$(url_port "$CANDIDATE_QDRANT_URL")"
fi

BASELINE_ENDPOINT="${BASELINE_ENDPOINT:-http://localhost:$BASELINE_API_PORT}"
CANDIDATE_ENDPOINT="${CANDIDATE_ENDPOINT:-http://localhost:$CANDIDATE_API_PORT}"
BASELINE_QDRANT_URL="${BASELINE_QDRANT_URL:-http://localhost:$BASELINE_QDRANT_PORT}"
CANDIDATE_QDRANT_URL="${CANDIDATE_QDRANT_URL:-http://localhost:$CANDIDATE_QDRANT_PORT}"
RUN_DIR="$EVALS_ROOT/data/sweep_runs/$RUN_ID"
PROBE_SCENARIO="$RUN_DIR/real_data_entity_repair_probes.json"

case "$REPAIR_MODE" in
    sync-only|reject-only|canonicalize-safe)
        ;;
    *)
        echo "ERROR: unsupported --repair-mode: $REPAIR_MODE" >&2
        exit 2
        ;;
esac

require_local_endpoint "baseline" "$BASELINE_ENDPOINT"
require_local_endpoint "candidate" "$CANDIDATE_ENDPOINT"

if [ "$REPAIR_MODE" != "sync-only" ]; then
    SYNC_BASELINE_FIRST=true
fi

stage_command_args() {
    local mode="$1"
    local suffix="$2"
    local run_migration="${3:-false}"
    local args=(
        "$SCRIPT_PATH"
        --automem-repo "$AUTOMEM_REPO"
        --run-id "$RUN_ID-$suffix"
        --scenario "$SCENARIO"
        --baseline-endpoint "$BASELINE_ENDPOINT"
        --candidate-endpoint "$CANDIDATE_ENDPOINT"
        --baseline-api-port "$BASELINE_API_PORT"
        --candidate-api-port "$CANDIDATE_API_PORT"
        --baseline-qdrant-url "$BASELINE_QDRANT_URL"
        --candidate-qdrant-url "$CANDIDATE_QDRANT_URL"
        --baseline-qdrant-port "$BASELINE_QDRANT_PORT"
        --candidate-qdrant-port "$CANDIDATE_QDRANT_PORT"
        --baseline-qdrant-grpc-port "$BASELINE_QDRANT_GRPC_PORT"
        --candidate-qdrant-grpc-port "$CANDIDATE_QDRANT_GRPC_PORT"
        --baseline-falkordb-port "$BASELINE_FALKORDB_PORT"
        --candidate-falkordb-port "$CANDIDATE_FALKORDB_PORT"
        --baseline-browser-port "$BASELINE_BROWSER_PORT"
        --candidate-browser-port "$CANDIDATE_BROWSER_PORT"
        --repair-mode "$mode"
        --audit-timeout-seconds "$AUDIT_TIMEOUT_SECONDS"
        --graph-update-timeout-seconds "$GRAPH_UPDATE_TIMEOUT_SECONDS"
        --qdrant-ready-timeout-seconds "$QDRANT_READY_TIMEOUT_SECONDS"
    )
    if [ -n "$SNAPSHOT" ]; then
        args+=(--snapshot "$SNAPSHOT")
    fi
    if [ "$STAGED_LOOP" = true ] || [ "$mode" != "sync-only" ]; then
        args+=(--sync-baseline-first)
    fi
    if [ "$SKIP_ENTITY_AUDIT" = true ]; then
        args+=(--skip-entity-audit)
    fi
    if [ "$FULL_ENTITY_AUDIT" = true ]; then
        args+=(--full-entity-audit)
    fi
    if [ "$SKIP_VECTOR_PREFLIGHT" = true ]; then
        args+=(--skip-vector-preflight)
    fi
    if [ "$SKIP_VECTOR_IDENTITY" = true ]; then
        args+=(--skip-vector-identity)
    fi
    if [ "$SKIP_RESTORE" = true ]; then
        args+=(--skip-restore)
    fi
    if [ "$run_migration" = true ]; then
        args+=(--run-entity-migration)
    fi
    if [ "$STRICT_PRESERVE_REVIEW" = true ]; then
        args+=(--strict-preserve-review)
    fi
    if [ "$CLEANUP_EXISTING_LAB_STACKS" = true ]; then
        args+=(--cleanup-existing-lab-stacks)
    fi
    printf '%q ' "bash" "${args[@]}"
    printf '\n'
}

run_stage_command() {
    local mode="$1"
    local suffix="$2"
    local run_migration="${3:-false}"
    local cmd
    cmd="$(stage_command_args "$mode" "$suffix" "$run_migration")"
    if [ "$PRINT_STAGED_LOOP" = true ]; then
        printf '%s' "$cmd"
    else
        eval "$cmd"
    fi
}

if [ "$STAGED_LOOP" = true ]; then
    if [ -z "$SNAPSHOT" ] && [ "$SKIP_RESTORE" = false ]; then
        echo "ERROR: --snapshot is required for --staged-loop unless --skip-restore is set." >&2
        exit 2
    fi
    run_stage_command sync-only sync-only false
    run_stage_command reject-only reject-only false
    run_stage_command canonicalize-safe canonicalize-safe false
    run_stage_command canonicalize-safe post-migration true
    exit 0
fi

write_probe_scenario() {
    mkdir -p "$RUN_DIR"
    python3 -c '
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
scenario_arg = sys.argv[2]
out_path = pathlib.Path(sys.argv[3])

scenario_path = pathlib.Path(scenario_arg)
if not scenario_path.exists():
    scenario_path = root / "scenarios" / f"{scenario_arg}.json"

scenario = json.loads(scenario_path.read_text())
scenario["description"] = (
    "Local real-data entity repair probes copied from "
    f"{scenario_path.relative_to(root) if scenario_path.is_relative_to(root) else scenario_path}. "
    "Generated under data/sweep_runs so production-derived probe artifacts stay ignored."
)
scenario["source_scenario"] = str(
    scenario_path.relative_to(root) if scenario_path.is_relative_to(root) else scenario_path
)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(scenario, indent=2) + "\n")
print(out_path)
' "$EVALS_ROOT" "$SCENARIO" "$PROBE_SCENARIO"
}

curl_json() {
    local endpoint="$1"
    local path="$2"
    local out="$3"
    local timeout_seconds="${4:-30}"
    if ! curl -fsS -H "X-Api-Key: $TOKEN" -H "X-Admin-Token: $ADMIN_TOKEN" \
        --max-time "$timeout_seconds" \
        "${endpoint%/}$path" -o "$out"; then
        echo "{}" > "$out"
    fi
}

wait_qdrant_ready() {
    local label="$1"
    local qdrant_url="$2"
    local deadline
    local now
    deadline=$(( $(date +%s) + ${QDRANT_READY_TIMEOUT_SECONDS%.*} ))
    while true; do
        if curl -fsS --max-time 5 \
            "${qdrant_url%/}/collections/$QDRANT_COLLECTION" >/dev/null; then
            echo "qdrant_ready_${label}: $qdrant_url"
            return 0
        fi
        now=$(date +%s)
        if [ "$now" -ge "$deadline" ]; then
            echo "ERROR: Qdrant $label was not ready after ${QDRANT_READY_TIMEOUT_SECONDS}s: $qdrant_url" >&2
            return 2
        fi
        sleep "$QDRANT_READY_RETRY_DELAY_SECONDS"
    done
}

wait_api_ready() {
    local label="$1"
    local endpoint="$2"
    local health_out="$RUN_DIR/${label}-api-ready-health.json"
    local deadline
    local now
    deadline=$(( $(date +%s) + ${API_READY_TIMEOUT_SECONDS%.*} ))
    while true; do
        if curl -fsS -H "X-Api-Key: $TOKEN" -H "X-Admin-Token: $ADMIN_TOKEN" \
            --max-time 10 \
            "${endpoint%/}/health" -o "$health_out"; then
            if python3 - "$health_out" <<'PY'; then
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    health = json.load(handle)

status = health.get("status")
memory_count = health.get("memory_count")
vector_count = health.get("vector_count")
qdrant = health.get("qdrant", {})
falkordb = health.get("falkordb", {})
qdrant_status = qdrant.get("status") if isinstance(qdrant, dict) else qdrant
falkordb_status = falkordb.get("status") if isinstance(falkordb, dict) else falkordb

healthy = (
    status == "healthy"
    and qdrant_status == "connected"
    and falkordb_status == "connected"
    and memory_count == vector_count
    and isinstance(memory_count, int)
    and memory_count > 0
)
raise SystemExit(0 if healthy else 1)
PY
                echo "api_ready_${label}: $endpoint"
                return 0
            fi
        fi
        now=$(date +%s)
        if [ "$now" -ge "$deadline" ]; then
            echo "ERROR: API $label was not ready after ${API_READY_TIMEOUT_SECONDS}s: $endpoint" >&2
            if [ -f "$health_out" ]; then
                cat "$health_out" >&2 || true
                printf '\n' >&2
            fi
            return 2
        fi
        sleep 3
    done
}

stop_port_listener() {
    local port="$1"
    local existing_pids
    existing_pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$existing_pids" ]; then
        echo "stopping_existing_listener:$port:$existing_pids"
        kill $existing_pids 2>/dev/null || true
        sleep 1
    fi
}

start_local_api() {
    local label="$1"
    local port="$2"
    local falkordb_port="$3"
    local qdrant_url="$4"
    local endpoint="$5"
    local log="$RUN_DIR/${label}-api.log"
    local pid_file="$RUN_DIR/${label}-api.pid"
    local pid

    stop_port_listener "$port"
    (
        cd "$AUTOMEM_REPO"
        PORT="$port" \
        FLASK_ENV=development \
        FLASK_DEBUG=0 \
        FALKORDB_HOST=localhost \
        FALKORDB_PORT="$falkordb_port" \
        QDRANT_URL="$qdrant_url" \
        QDRANT_TIMEOUT_SECONDS="${QDRANT_TIMEOUT_SECONDS:-60}" \
        QDRANT_ENSURE_PAYLOAD_INDEXES=false \
        AUTOMEM_API_TOKEN="$TOKEN" \
        ADMIN_API_TOKEN="$ADMIN_TOKEN" \
        CONSOLIDATION_DECAY_INTERVAL_SECONDS=0 \
        CONSOLIDATION_ENTITY_INTERVAL_SECONDS=0 \
        CONSOLIDATION_IDENTITY_INTERVAL_SECONDS=0 \
        IDENTITY_SYNTHESIS_ENABLED=false \
        "$AUTOMEM_PYTHON" app.py
    ) > "$log" 2>&1 &
    pid=$!
    LOCAL_API_PIDS+=("$pid")
    echo "$pid" > "$pid_file"
    wait_api_ready "$label" "$endpoint"
}

capture_audit() {
    local endpoint="$1"
    local out="$2"
    if [ "$SKIP_ENTITY_AUDIT" = true ]; then
        echo '{"skipped":true}' > "$out"
        return
    fi
    if [ "$FULL_ENTITY_AUDIT" = true ]; then
        curl_json "$endpoint" "/entities/audit" "$out" "$AUDIT_TIMEOUT_SECONDS"
    else
        curl_json "$endpoint" "/entities/audit?summary=true&limit=50" "$out" "$AUDIT_TIMEOUT_SECONDS"
    fi
}

run_vector_identity() {
    local label="$1"
    local out="$2"
    if [ "$SKIP_VECTOR_IDENTITY" = true ]; then
        echo '{"skipped":true}' > "$out"
        return
    fi
    wait_qdrant_ready "baseline_$label" "$BASELINE_QDRANT_URL"
    wait_qdrant_ready "candidate_$label" "$CANDIDATE_QDRANT_URL"
    python3 "$EVALS_ROOT/runners/vector_identity.py" \
        --baseline-qdrant-url "$BASELINE_QDRANT_URL" \
        --candidate-qdrant-url "$CANDIDATE_QDRANT_URL" \
        --collection "$QDRANT_COLLECTION" \
        --batch-size "${VECTOR_IDENTITY_BATCH_SIZE:-64}" \
        --timeout-seconds "${VECTOR_IDENTITY_TIMEOUT_SECONDS:-180}" \
        --retries "${VECTOR_IDENTITY_RETRIES:-20}" \
        --retry-delay-seconds "${VECTOR_IDENTITY_RETRY_DELAY_SECONDS:-3}" \
        --out "$out" >/dev/null
    echo "vector_identity_$label: $out"
}

run_repair_plan() {
    local label="$1"
    local mode="$2"
    local falkordb_port="$3"
    local qdrant_url="$4"
    local report_dir="$5"

    (
        cd "$AUTOMEM_REPO"
        FALKORDB_HOST=localhost \
        FALKORDB_PORT="$falkordb_port" \
        QDRANT_URL="$qdrant_url" \
        AUTOMEM_API_TOKEN="$TOKEN" \
        ADMIN_API_TOKEN="$ADMIN_TOKEN" \
        "$AUTOMEM_PYTHON" scripts/lab/repair_entity_tags.py \
            --batch-size "$BATCH_SIZE" \
            --mode "$mode" \
            --report-dir "$report_dir"

        FALKORDB_HOST=localhost \
        FALKORDB_PORT="$falkordb_port" \
        QDRANT_URL="$qdrant_url" \
        AUTOMEM_API_TOKEN="$TOKEN" \
        ADMIN_API_TOKEN="$ADMIN_TOKEN" \
        "$AUTOMEM_PYTHON" scripts/lab/repair_entity_tags.py \
            --execute \
            --plan "$report_dir/plan.jsonl" \
            --batch-size "$BATCH_SIZE" \
            --graph-update-timeout-seconds "$GRAPH_UPDATE_TIMEOUT_SECONDS"
    )
    echo "repair_${label}: $report_dir"
}

compare_recall() {
    local label="$1"
    local run_dir="$2"
    local report="$3"
    local args=(
        "$EVALS_ROOT/runners/compare_recall_endpoints.py"
        --scenario "$PROBE_SCENARIO"
        --baseline-endpoint "$BASELINE_ENDPOINT"
        --candidate-endpoint "$CANDIDATE_ENDPOINT"
        --token "$TOKEN"
        --run-dir "$run_dir"
        --report "$report"
        --fail-on-preserve-regression
        --baseline-qdrant-url "$BASELINE_QDRANT_URL"
        --candidate-qdrant-url "$CANDIDATE_QDRANT_URL"
        --qdrant-collection "$QDRANT_COLLECTION"
    )
    if [ "$SKIP_VECTOR_PREFLIGHT" = true ]; then
        args+=(--skip-vector-preflight)
    fi
    if [ "$STRICT_PRESERVE_REVIEW" = true ]; then
        args+=(--fail-on-preserve-review)
    fi
    wait_qdrant_ready "baseline_${label}" "$BASELINE_QDRANT_URL"
    wait_qdrant_ready "candidate_${label}" "$CANDIDATE_QDRANT_URL"
    RECALL_COMPARE_HTTP_RETRIES="${RECALL_COMPARE_HTTP_RETRIES:-5}" \
    RECALL_COMPARE_HTTP_RETRY_DELAY_SECONDS="${RECALL_COMPARE_HTTP_RETRY_DELAY_SECONDS:-3}" \
        python3 "${args[@]}"
    echo "recall_compare_$label: $report"
}

if [ "$WRITE_PROBES_ONLY" = true ]; then
    write_probe_scenario >/dev/null
    echo "probes: $PROBE_SCENARIO"
    exit 0
fi

if [ -z "$SNAPSHOT" ] && [ "$SKIP_RESTORE" = false ]; then
    echo "ERROR: --snapshot is required unless --skip-restore is set." >&2
    exit 2
fi

if [ ! -d "$AUTOMEM_REPO" ]; then
    echo "ERROR: automem repo not found: $AUTOMEM_REPO" >&2
    exit 2
fi

AUTOMEM_PYTHON="${AUTOMEM_PYTHON:-$AUTOMEM_REPO/.venv/bin/python}"
if [ ! -x "$AUTOMEM_PYTHON" ]; then
    AUTOMEM_PYTHON="python3"
fi

mkdir -p "$RUN_DIR"
write_probe_scenario >/dev/null

if [ "$CLEANUP_EXISTING_LAB_STACKS" = true ] && [ "$SKIP_RESTORE" = false ]; then
    cleanup_existing_lab_stacks
fi

if [ "$SKIP_RESTORE" = false ]; then
    bash "$AUTOMEM_REPO/scripts/lab/clone_production.sh" \
        --restore-only "$SNAPSHOT" \
        --compose-project "$BASELINE_COMPOSE_PROJECT" \
        --api-port "$BASELINE_API_PORT" \
        --qdrant-port "$BASELINE_QDRANT_PORT" \
        --qdrant-grpc-port "$BASELINE_QDRANT_GRPC_PORT" \
        --falkordb-port "$BASELINE_FALKORDB_PORT" \
        --falkordb-browser-port "$BASELINE_BROWSER_PORT" \
        --skip-api

    bash "$AUTOMEM_REPO/scripts/lab/clone_production.sh" \
        --restore-only "$SNAPSHOT" \
        --compose-project "$CANDIDATE_COMPOSE_PROJECT" \
        --api-port "$CANDIDATE_API_PORT" \
        --qdrant-port "$CANDIDATE_QDRANT_PORT" \
        --qdrant-grpc-port "$CANDIDATE_QDRANT_GRPC_PORT" \
        --falkordb-port "$CANDIDATE_FALKORDB_PORT" \
        --falkordb-browser-port "$CANDIDATE_BROWSER_PORT" \
        --skip-api

    start_local_api baseline \
        "$BASELINE_API_PORT" \
        "$BASELINE_FALKORDB_PORT" \
        "$BASELINE_QDRANT_URL" \
        "$BASELINE_ENDPOINT"
    start_local_api candidate \
        "$CANDIDATE_API_PORT" \
        "$CANDIDATE_FALKORDB_PORT" \
        "$CANDIDATE_QDRANT_URL" \
        "$CANDIDATE_ENDPOINT"
fi

REPAIR_DIR="$AUTOMEM_REPO/lab/results/entity-tag-repair/$RUN_ID"
BASELINE_SYNC_REPAIR_DIR="$AUTOMEM_REPO/lab/results/entity-tag-repair/$RUN_ID-baseline-sync"
if [ "$SYNC_BASELINE_FIRST" = true ]; then
    run_repair_plan \
        "baseline_sync" \
        "sync-only" \
        "$BASELINE_FALKORDB_PORT" \
        "$BASELINE_QDRANT_URL" \
        "$BASELINE_SYNC_REPAIR_DIR"
fi

curl_json "$BASELINE_ENDPOINT" "/health" "$RUN_DIR/baseline-health.json"
capture_audit "$BASELINE_ENDPOINT" "$RUN_DIR/baseline-entities-audit.json"

run_repair_plan \
    "candidate" \
    "$REPAIR_MODE" \
    "$CANDIDATE_FALKORDB_PORT" \
    "$CANDIDATE_QDRANT_URL" \
    "$REPAIR_DIR"

curl_json "$CANDIDATE_ENDPOINT" "/health" "$RUN_DIR/candidate-health.json"
capture_audit "$CANDIDATE_ENDPOINT" "$RUN_DIR/candidate-entities-audit.json"
run_vector_identity "pre_compare" "$RUN_DIR/vector-identity.json"

compare_recall "pre_migration" "$RUN_DIR/recall-compare" "$RUN_DIR/recall-comparison.md"

if [ "$RUN_ENTITY_MIGRATION" = true ]; then
    MIGRATION_LOG="$RUN_DIR/entity-migration.log"
    if ! (
        cd "$AUTOMEM_REPO"
        FALKORDB_HOST=localhost \
        FALKORDB_PORT="$CANDIDATE_FALKORDB_PORT" \
        "$AUTOMEM_PYTHON" scripts/migrate_entity_nodes.py
    ) > "$MIGRATION_LOG" 2>&1; then
        echo "ERROR: Entity migration failed; log: $MIGRATION_LOG" >&2
        tail -n 80 "$MIGRATION_LOG" >&2 || true
        exit 1
    fi
    echo "entity_migration_log: $MIGRATION_LOG"
    tail -n 40 "$MIGRATION_LOG"
    capture_audit "$CANDIDATE_ENDPOINT" "$RUN_DIR/candidate-entities-audit-post-migration.json"
    run_vector_identity "post_migration" "$RUN_DIR/vector-identity-post-migration.json"
    compare_recall \
        "post_migration" \
        "$RUN_DIR/recall-compare-post-migration" \
        "$RUN_DIR/recall-comparison-post-migration.md"
fi

printf '%s\n' \
    "# Real Data Entity Repair Eval" \
    "" \
    "- Baseline: $BASELINE_ENDPOINT" \
    "- Candidate: $CANDIDATE_ENDPOINT" \
    "- Repair mode: $REPAIR_MODE" \
    "- Entity audit skipped: $SKIP_ENTITY_AUDIT" \
    "- Vector preflight skipped: $SKIP_VECTOR_PREFLIGHT" \
    "- Vector identity skipped: $SKIP_VECTOR_IDENTITY" \
    "- Baseline sync first: $SYNC_BASELINE_FIRST" \
    "- Full entity audit: $FULL_ENTITY_AUDIT" \
    "- Strict preserve review: $STRICT_PRESERVE_REVIEW" \
    "- Baseline sync artifacts: $BASELINE_SYNC_REPAIR_DIR" \
    "- Entity migration run: $RUN_ENTITY_MIGRATION" \
    "- Entity migration log: $RUN_DIR/entity-migration.log" \
    "- Repair artifacts: $REPAIR_DIR" \
    "- Probe scenario: $PROBE_SCENARIO" \
    "- Recall comparison: $RUN_DIR/recall-comparison.md" \
    > "$RUN_DIR/README.md"

echo "run_dir: $RUN_DIR"
echo "repair_dir: $REPAIR_DIR"
