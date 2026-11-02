#!/usr/bin/env bash
# LD-397: verify the local Docker Compose MVP environment, including Code Analyzer.
# Usage: ./scripts/verify-compose.sh [--no-up]
#   --no-up   do not (re)build/start the stack, only verify what is already running.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f compose.yaml"
TIMEOUT="${VERIFY_TIMEOUT:-300}"

pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1" >&2; exit 1; }

wait_healthy() {
  local svc="$1" cid status elapsed=0
  while (( elapsed < TIMEOUT )); do
    cid="$($COMPOSE ps -q "$svc")"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
      [[ "$status" == "healthy" || "$status" == "running" ]] && return 0
    fi
    sleep 3; elapsed=$((elapsed + 3))
  done
  return 1
}

echo "1. Validate compose file"
$COMPOSE config --quiet && pass "compose.yaml is valid"

if [[ "${1:-}" != "--no-up" ]]; then
  echo "2. docker compose up --build"
  $COMPOSE up --build -d
fi

echo "3. Service health (docker healthcheck)"
for svc in backend-db github-db code-analyzer ai-service github-integration backend frontend; do
  wait_healthy "$svc" && pass "$svc is healthy/running" || fail "$svc did not become healthy within ${TIMEOUT}s"
done

echo "4. Code Analyzer from the host"
curl -fsS http://localhost:8000/health | grep -q "\"status\":\"ok\"" && pass "GET /health on :8000"

echo "5. Backend -> Analyzer by service name (from github-integration container)"
$COMPOSE exec -T github-integration curl -fsS http://code-analyzer:8000/health | grep -q '"status":"ok"' \
  && pass "github-integration reaches http://code-analyzer:8000/health"
RESP="$($COMPOSE exec -T github-integration curl -fsS -X POST http://code-analyzer:8000/api/v1/analyze-repo \
  -H 'Content-Type: application/json' \
  -d '{"target":"verify/repo","scope":"repository","files":[{"path":"a.py","content":"def add(a, b):\n    return a + b\n","language":"python"}]}')"
echo "$RESP" | grep -q '"status":"ok"' && pass "POST /api/v1/analyze-repo through service DNS name" \
  || fail "unexpected analyzer response: $RESP"

echo "6. Other services"
curl -fsS http://localhost:8001/health >/dev/null && pass "ai-service /health"
$COMPOSE exec -T github-integration curl -fsS http://localhost:8082/actuator/health >/dev/null && pass "github-integration /actuator/health"
curl -fsS http://localhost:8080/actuator/health >/dev/null && pass "backend /actuator/health"
curl -fsS -o /dev/null http://localhost:3000/ && pass "frontend serves /"

echo; echo "All checks passed."
