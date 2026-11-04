#!/usr/bin/env bash
# One arm of the issue #83 bench on a fresh isolated stack (cold: ingest -> drain -> recall, no maintenance).
#   AUTOMEM_SRC=/path/to/automem scripts/benchmarks/run_meili_arm.sh baseline|keyword_swap [conv]
# Ports are offset (18001/16333/16379/17700) so a developer's own AutoMem stack is never touched.
set -euo pipefail
ARM=${1:?arm: baseline|keyword_swap}
CONV=${2:-0}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
: "${AUTOMEM_SRC:?set AUTOMEM_SRC to the automem checkout (pinned commit in configs/meilisearch/arms.json)}"
export AUTOMEM_SRC MEILI_ARM=$ARM
SUFFIX=${KEYWORD_ONLY:+-kwonly} # KEYWORD_ONLY=1: vector leg returns nothing, so /recall is the keyword leg alone
export MEILI_KEYWORD_ONLY=${KEYWORD_ONLY:-}
PROJECT=meilibench-$ARM$SUFFIX
OUT=${OUT:-$ROOT/data/results/meilisearch-bench}
DATA=${LOCOMO_DATA:-$AUTOMEM_SRC/tests/benchmarks/locomo/data/locomo10.json}
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/configs/meilisearch/docker-compose.yml")
mkdir -p "$OUT"

"${COMPOSE[@]}" down -v >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d
python3.12 - <<'PY'
import time, urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen("http://localhost:18001/health", timeout=3); raise SystemExit(0)
    except Exception:
        time.sleep(3)
raise SystemExit("AutoMem never became healthy")
PY
MEILI_FLAGS=()
[ "$ARM" != baseline ] && MEILI_FLAGS=(--meili-url http://localhost:17700)
python3.12 "$ROOT/scripts/benchmarks/meili_bench.py" locomo --data "$DATA" --conv "$CONV" \
  --endpoint http://localhost:18001 --project "$PROJECT" --top-k 10 \
  --out "$OUT/$ARM$SUFFIX-locomo-conv$CONV.json" "${MEILI_FLAGS[@]}"
"${COMPOSE[@]}" down -v
