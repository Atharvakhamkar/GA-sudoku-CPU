#!/usr/bin/env bash
# =====================================================================
# run_experiment.sh  (deterministic — starts workers by hand)
# ---------------------------------------------------------------------
# Fixed worker count per run, with NO compose --scale (which was silently
# removing the extra replicas). We start EXACTLY N worker containers with
# `docker run`, all sharing the "fitness-pool" network alias, so nothing
# can drop them. The autoscaler is never started.
#
# Usage:   ./scripts/run_experiment.sh "1 2 3 4 6"
# =====================================================================
set -euo pipefail

WORKER_COUNTS="${1:-1 2 3 4 6}"
cd "$(dirname "$0")/.."

NET="ga-net"
ALIAS="fitness-pool"

# Load .env so workers + GA share the same settings
set -a; [ -f .env ] && . ./.env; set +a

echo "=== Building images ==="
docker compose build fitness-pool ga-service >/dev/null

# Auto-detect the built image names (handles ga-sudoku / ga_sudoku / any folder)
FIT_IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'fitness(-pool)?:' | grep -v '<none>' | head -1)
GA_IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'ga-service:' | grep -v '<none>' | head -1)
# Fallbacks
[ -z "${FIT_IMG:-}" ] && FIT_IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep fitness | head -1)
[ -z "${GA_IMG:-}" ]  && GA_IMG=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep ga-service | head -1)

echo "  fitness image: $FIT_IMG"
echo "  ga image:      $GA_IMG"
if [ -z "$FIT_IMG" ] || [ -z "$GA_IMG" ]; then
  echo "ERROR: could not find built images. Run 'docker compose build' first."; exit 1
fi

docker network create "$NET" 2>/dev/null || true
cleanup_workers() { docker ps -aq --filter "label=ga.exp=worker" | xargs -r docker rm -f >/dev/null 2>&1 || true; }

for N in $WORKER_COUNTS; do
  echo ""
  echo "=========================================="
  echo "  RUN: $N fitness worker(s)"
  echo "=========================================="
  cleanup_workers
  rm -f results/status.json results/result.json

  for i in $(seq 1 "$N"); do
    docker run -d --rm --name "exp-fitness-$i" \
      --network "$NET" --network-alias "$ALIAS" --label "ga.exp=worker" \
      -e EVAL_DELAY_MS="${EVAL_DELAY_MS:-25}" \
      "$FIT_IMG" >/dev/null
  done
  echo "  started $N worker container(s); waiting for health..."
  sleep 8
  UP=$(docker ps --filter "label=ga.exp=worker" --filter "status=running" -q | wc -l | tr -d ' ')
  echo "  >>> workers actually running: $UP  (should be $N)"

  docker run --rm --network "$NET" \
    -e PUZZLE="${PUZZLE:-classic}" -e MAX_GENERATIONS="${MAX_GENERATIONS:-120}" \
    -e POP_SIZE="${POP_SIZE:-2000}" -e MUTATION_RATE="${MUTATION_RATE:-0.25}" \
    -e CROSSOVER_RATE="${CROSSOVER_RATE:-0.85}" -e TOURNAMENT_K="${TOURNAMENT_K:-5}" \
    -e ELITE_COUNT="${ELITE_COUNT:-6}" -e SEED="${SEED:-7}" \
    -e HYPERMUTATION_FACTOR="${HYPERMUTATION_FACTOR:-10}" \
    -e STAGNATION_FOR_HYPERMUT="${STAGNATION_FOR_HYPERMUT:-25}" \
    -e STAGNATION_FOR_RESTART="${STAGNATION_FOR_RESTART:-80}" \
    -e EVAL_CONCURRENCY="${EVAL_CONCURRENCY:-6}" -e RATE_WINDOW="${RATE_WINDOW:-5}" \
    -e REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-300}" \
    -e STAGNATION_THRESHOLD="${STAGNATION_THRESHOLD:-0.2}" \
    -e FITNESS_URL="http://fitness-pool:8001" \
    -e STATUS_PATH="/results/status.json" -e RESULT_PATH="/results/result.json" \
    -e PUZZLE_PATH="/results/puzzle.json" \
    -v "$(pwd)/results:/results" \
    "$GA_IMG"

  cp results/result.json "results/result_workers_${N}.json"
  echo "  saved -> results/result_workers_${N}.json"
  cleanup_workers
done

echo ""
echo "=== All runs complete. Analysing... ==="
python3 scripts/analyze_results.py
