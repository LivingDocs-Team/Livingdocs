#!/usr/bin/env bash
# LD-404: Release Smoke Testing & Deployment Verification
# Usage:
#   ./scripts/verify-compose.sh --clean   # Clean deployment (down -v -> up --build), E2E smoke, restart & persistence
#   ./scripts/verify-compose.sh           # Build/start stack, E2E smoke, restart & persistence
#   ./scripts/verify-compose.sh --no-up   # Verify already running stack + restart & persistence
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f compose.yaml"
TIMEOUT="${VERIFY_TIMEOUT:-300}"
MODE="${1:-default}"
REPORT_DIR="${SMOKE_REPORT_DIR:-artifacts}"
REPORT_FILE="$REPORT_DIR/ld-404-smoke-report.log"

mkdir -p "$REPORT_DIR"
: > "$REPORT_FILE"

log()  { printf '%s\n' "$1" | tee -a "$REPORT_FILE"; }
pass() { printf '  [PASS] %s\n' "$1" | tee -a "$REPORT_FILE"; }
fail() { printf '  [FAIL] %s\n' "$1" | tee -a "$REPORT_FILE" >&2; exit 1; }

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

wait_all_healthy() {
  for svc in backend-db github-db code-analyzer ai-service github-integration backend frontend; do
    wait_healthy "$svc" && pass "$svc is healthy/running" || fail "$svc did not become healthy within ${TIMEOUT}s"
  done
}

# Load .env neu co de lay GITHUB_INTEGRATION_INTERNAL_SECRET
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

log "=== LD-404 Release Smoke & Deployment Verification ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

log "1. Validate compose configuration"
$COMPOSE config --quiet && pass "compose.yaml is valid"

if [[ "$MODE" == "--clean" ]]; then
  log "2. Clean deployment: tearing down existing containers & volumes"
  $COMPOSE down -v --remove-orphans
  pass "Removed old containers and volumes"
fi

if [[ "$MODE" != "--no-up" ]]; then
  log "3. Starting stack with docker compose up --build -d"
  $COMPOSE up --build -d
fi

log "4. Waiting for all services to become healthy"
wait_all_healthy

log "5. Verifying database migrations"
# 5a. GitHub Integration Flyway migrations (github-db)
FLYWAY_OK="$($COMPOSE exec -T github-db psql -U livingdocs -d github_integration -tAc \
  "SELECT COUNT(*) FROM flyway_schema_history WHERE success = true;" 2>/dev/null || echo "0")"
[[ "${FLYWAY_OK// /}" -gt 0 ]] \
  && pass "github-db Flyway migrations applied (${FLYWAY_OK// /} successful versions)" \
  || fail "github-db Flyway migrations missing or failed"

FLYWAY_FAILED="$($COMPOSE exec -T github-db psql -U livingdocs -d github_integration -tAc \
  "SELECT COUNT(*) FROM flyway_schema_history WHERE success = false;" 2>/dev/null || echo "1")"
[[ "${FLYWAY_FAILED// /}" -eq 0 ]] \
  && pass "github-db has 0 failed Flyway migrations" \
  || fail "github-db has failed Flyway migrations"

# 5b. Backend schema initialization (backend-db, Hibernate ddl-auto=update)
BACKEND_TABLES="$($COMPOSE exec -T backend-db psql -U livingdocs -d cnpm -tAc \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")"
[[ "${BACKEND_TABLES// /}" -gt 0 ]] \
  && pass "backend-db schema initialized (${BACKEND_TABLES// /} tables in cnpm)" \
  || fail "backend-db schema has no tables"

log "6. Verifying service health & internal connectivity"
curl -fsS http://localhost:8000/health | grep -q '"status":"ok"' && pass "code-analyzer /health (:8000)"
curl -fsS http://localhost:8001/health | grep -q '"status":"ok"' && pass "ai-service /health (:8001)"
$COMPOSE exec -T github-integration curl -fsS http://localhost:8082/actuator/health >/dev/null \
  && pass "github-integration /actuator/health (:8082)"
curl -fsS http://localhost:8080/actuator/health >/dev/null && pass "backend /actuator/health (:8080)"
curl -fsS -o /dev/null http://localhost:3000/ && pass "frontend serves / (:3000)"

log "7. Running Pre-Restart E2E Smoke Test (Generation & Review)"
python3 scripts/release_smoke_test.py \
  --phase pre-restart \
  --state-file "$REPORT_DIR/smoke-state.json" \
  --report-file "$REPORT_DIR/smoke-e2e-results.json" | tee -a "$REPORT_FILE"

log "8. Restarting application services for recovery verification"
$COMPOSE restart code-analyzer ai-service github-integration backend frontend
wait_all_healthy

log "9. Running Post-Restart Persistence Verification"
python3 scripts/release_smoke_test.py \
  --phase post-restart \
  --state-file "$REPORT_DIR/smoke-state.json" \
  --report-file "$REPORT_DIR/smoke-e2e-results.json" | tee -a "$REPORT_FILE"

log "=== ALL LD-404 RELEASE SMOKE & PERSISTENCE CHECKS PASSED ==="
log "Recorded results saved to: $REPORT_FILE and $REPORT_DIR/smoke-e2e-results.json"