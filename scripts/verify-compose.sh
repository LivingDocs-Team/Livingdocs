#!/usr/bin/env bash
# LD-404: Release Smoke Testing & Deployment Verification
# Usage:
#   ./scripts/verify-compose.sh --clean   # Clean deployment (down -v -> up --build), E2E smoke, restart & persistence
#   ./scripts/verify-compose.sh           # Build/start stack, E2E smoke, restart & persistence
#   ./scripts/verify-compose.sh --no-up   # Verify already running stack + restart & persistence

set -euo pipefail
cd "$(dirname "$0")/.."

# === P1 FIX: Dùng project name riêng cho smoke test ===
# Không dùng project mặc định (tên thư mục) để tránh xóa volume của stack đang vận hành.
SMOKE_PROJECT="${SMOKE_PROJECT:-livingdocs-smoke}"
COMPOSE=(docker compose -p "${SMOKE_PROJECT}" -f compose.yaml)

# === P1 FIX: Ánh xạ cổng riêng để tránh xung đột với stack dev ===
export BACKEND_DB_PORT="${SMOKE_BACKEND_DB_PORT:-5444}"
export GITHUB_DB_PORT="${SMOKE_GITHUB_DB_PORT:-5443}"
export BACKEND_PORT="${SMOKE_BACKEND_PORT:-8081}"
export FRONTEND_PORT="${SMOKE_FRONTEND_PORT:-3001}"
export AI_SERVICE_PORT="${SMOKE_AI_SERVICE_PORT:-8002}"
export ANALYZER_PORT="${SMOKE_ANALYZER_PORT:-8003}"
export GITHUB_INTEGRATION_PORT="${SMOKE_GITHUB_INTEGRATION_PORT:-8083}"

export FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
export BACKEND_URL="http://localhost:${BACKEND_PORT}"
export ANALYZER_URL="http://localhost:${ANALYZER_PORT}"
export AI_SERVICE_URL="http://localhost:${AI_SERVICE_PORT}"
export GITHUB_INTEGRATION_URL="http://localhost:${GITHUB_INTEGRATION_PORT}"

TIMEOUT="${VERIFY_TIMEOUT:-300}"
MODE="${1:-default}"
REPORT_DIR="${SMOKE_REPORT_DIR:-artifacts}"
REPORT_FILE="$REPORT_DIR/ld-404-smoke-report.log"
mkdir -p "$REPORT_DIR"
: > "$REPORT_FILE"

# === P2 FIX: State file nằm trong thư mục tạm bảo mật (700) ===
SMOKE_STATE_DIR="${SMOKE_STATE_DIR:-$(mktemp -d -t ld404-smoke-state.XXXXXX)}"
chmod 700 "$SMOKE_STATE_DIR"
export SMOKE_STATE_FILE="${SMOKE_STATE_FILE:-$SMOKE_STATE_DIR/smoke-state.json}"

log()  { printf '%s\n' "$1" | tee -a "$REPORT_FILE"; }
pass() { printf ' [PASS] %s\n' "$1" | tee -a "$REPORT_FILE"; }
fail() { printf ' [FAIL] %s\n' "$1" | tee -a "$REPORT_FILE" >&2; exit 1; }

wait_healthy() {
  local svc="$1"
  local cid status elapsed=0
  while (( elapsed < TIMEOUT )); do
    cid="$("${COMPOSE[@]}" ps -q "$svc" 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)"
      [[ "$status" == "healthy" || "$status" == "running" ]] && return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  return 1
}

wait_all_healthy() {
  for svc in backend-db github-db code-analyzer ai-service github-integration backend frontend; do
    if wait_healthy "$svc"; then
      pass "$svc is healthy/running"
    else
      fail "$svc did not become healthy within ${TIMEOUT}s"
    fi
  done
}

# Load .env nếu có
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

log "=== LD-404 Release Smoke & Deployment Verification ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
log "Smoke project: ${SMOKE_PROJECT}"
log "State file (secure, tmp): ${SMOKE_STATE_FILE}"

log "1. Validate compose configuration"
"${COMPOSE[@]}" config --quiet && pass "compose.yaml is valid"

# === P1 FIX: Chỉ xóa volume trong project smoke ===
if [[ "$MODE" == "--clean" ]]; then
  log "2. Clean deployment: tearing down smoke project (project: ${SMOKE_PROJECT})"
  "${COMPOSE[@]}" down -v --remove-orphans
  pass "Removed old smoke project containers and volumes (project: ${SMOKE_PROJECT})"
fi

if [[ "$MODE" != "--no-up" ]]; then
  log "3. Starting stack with docker compose up --build -d (project: ${SMOKE_PROJECT})"
  "${COMPOSE[@]}" up --build -d
fi

log "4. Waiting for all services to become healthy"
wait_all_healthy

log "5. Verifying database migrations"
FLYWAY_OK="$("${COMPOSE[@]}" exec -T github-db psql -U livingdocs -d github_integration -tAc \
  "SELECT COUNT(*) FROM flyway_schema_history WHERE success = true;" 2>/dev/null | tr -d '[:space:]' || echo "0")"
[[ "${FLYWAY_OK:-0}" -gt 0 ]] \
  && pass "github-db Flyway migrations applied (${FLYWAY_OK} successful versions)" \
  || fail "github-db Flyway migrations missing or failed"

FLYWAY_FAILED="$("${COMPOSE[@]}" exec -T github-db psql -U livingdocs -d github_integration -tAc \
  "SELECT COUNT(*) FROM flyway_schema_history WHERE success = false;" 2>/dev/null | tr -d '[:space:]' || echo "1")"
[[ "${FLYWAY_FAILED:-1}" -eq 0 ]] \
  && pass "github-db Flyway migrations have no failed versions" \
  || fail "github-db Flyway migrations contain failed versions"

log "6. Running pre-restart E2E smoke"
python3 scripts/release_smoke_test.py \
  --phase pre-restart \
  --state-file "$SMOKE_STATE_FILE" \
  --report-file "$REPORT_DIR/smoke-pre-restart-result.json" \
  || fail "pre-restart smoke failed"
pass "pre-restart smoke passed"

log "7. Restarting services (simulating redeploy)"
"${COMPOSE[@]}" restart
wait_all_healthy
pass "All services healthy after restart"

log "8. Running post-restart E2E persistence smoke"
python3 scripts/release_smoke_test.py \
  --phase post-restart \
  --state-file "$SMOKE_STATE_FILE" \
  --report-file "$REPORT_DIR/smoke-post-restart-result.json" \
  || fail "post-restart smoke failed"
pass "post-restart smoke passed"

# Cleanup state file an toàn
rm -f "$SMOKE_STATE_FILE" 2>/dev/null || true
rmdir "$SMOKE_STATE_DIR" 2>/dev/null || true

log "=== LD-404 smoke & deployment verification complete ==="
log "Report: ${REPORT_FILE}"