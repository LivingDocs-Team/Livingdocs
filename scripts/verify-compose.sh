#!/usr/bin/env bash
# LD-404: Release Smoke Testing & Deployment Verification
# Usage: ./scripts/verify-compose.sh [--clean|--no-build]
# All modes start a fresh project. Existing stacks are never reused.

set -euo pipefail
cd "$(dirname "$0")/.."

build_option=--build
case "${1:-}" in
  ""|--clean) ;;
  --no-build) build_option=--no-build ;;
  *) printf 'Usage: %s [--clean|--no-build] (fresh fixtures required)\n' "$0" >&2; exit 2 ;;
esac
(( $# <= 1 )) || exit 2

REPORT_DIR="${SMOKE_REPORT_DIR:-artifacts}"
REPORT_FILE="$REPORT_DIR/ld-404-smoke-report.log"
mkdir -p "$REPORT_DIR"
: > "$REPORT_FILE"

log()  { printf '%s\n' "$1" | tee -a "$REPORT_FILE"; }
pass() { printf ' [PASS] %s\n' "$1" | tee -a "$REPORT_FILE"; }
fail() { printf ' [FAIL] %s\n' "$1" | tee -a "$REPORT_FILE" >&2; exit 1; }

scratch="$(mktemp -d -t ld404.XXXXXXXXXXXX)"
export SMOKE_STATE_FILE="$scratch/smoke-state.json"
SMOKE_PROJECT="livingdocs-smoke-${scratch##*.}"
SMOKE_PROJECT="${SMOKE_PROJECT,,}"

# Use fixture credentials and ignore repository .env and inherited Compose settings.
unset COMPOSE_ENV_FILES COMPOSE_PROFILES COMPOSE_COMPATIBILITY
unset AI_SERVICE_INTERNAL_SECRET INTERNAL_API_SECRET
unset ANTHROPIC_API_KEY GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET GITHUB_WEBHOOK_SECRET
export TOKEN_ENCRYPTION_KEY="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
export GITHUB_INTEGRATION_INTERNAL_SECRET="smoke-test-internal-secret"
export SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_GITHUB_CLIENT_ID="smoke-test-placeholder"
export SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_GITHUB_CLIENT_SECRET="smoke-test-placeholder"
# Exercise the Compose default even if the caller has set a retention override.
unset ADMIN_USER_AUDIT_RETENTION_DAYS BACKEND_DB_PASSWORD
export GITHUB_CALLBACK_BIND_ADDRESS=127.0.0.1
export GITHUB_REDIRECT_URI=http://localhost:8083/api/github/callback
export BACKEND_PORT=8081 FRONTEND_PORT=3001 AI_SERVICE_PORT=8002 ANALYZER_PORT=8003 GITHUB_INTEGRATION_PORT=8083
export FRONTEND_URL=http://localhost:3001 BACKEND_URL=http://localhost:8081
export ANALYZER_URL=http://localhost:8003 AI_SERVICE_URL=http://localhost:8002
export GITHUB_INTEGRATION_URL=http://localhost:8083 SMOKE_ORIGIN=http://localhost:3000
export no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1
TIMEOUT="${VERIFY_TIMEOUT:-300}"

# Keep the backend database credentials and healthcheck from compose.yaml.
# Neither smoke database publishes a host port.
cat > "$scratch/fixture.yaml" <<'YAML'
services:
  backend-db:
    ports: !reset []
  github-db:
    ports: !reset []
    healthcheck:
      test: ["CMD", "pg_isready", "-h", "127.0.0.1", "-U", "livingdocs", "-d", "github_integration"]
YAML
DOCKER=(docker --context default)
COMPOSE=("${DOCKER[@]}" compose --env-file /dev/null -p "$SMOKE_PROJECT" -f compose.yaml -f "$scratch/fixture.yaml")

owns_project=false
legacy_started=false
cleanup() {
  local status=$? volume name identity
  trap - EXIT
  trap '' INT TERM
  if [[ "$owns_project" == true ]]; then
    if [[ "$status" != 0 ]]; then
      "${COMPOSE[@]}" ps --all >> "$REPORT_FILE" 2>&1 || true
      "${COMPOSE[@]}" logs --no-color --tail 80 >> "$REPORT_FILE" 2>&1 || true
    fi
    if [[ "$legacy_started" == true ]]; then
      "${DOCKER[@]}" container rm -f "$SMOKE_PROJECT-legacy" >/dev/null || status=1
    fi
    if "${COMPOSE[@]}" down; then
      for volume in backend-db-data github-db-data ai-templates analyzer-data; do
        name="${SMOKE_PROJECT}_$volume"
        if identity="$("${DOCKER[@]}" volume inspect -f '{{ index .Labels "com.docker.compose.project" }}|{{ index .Labels "com.docker.compose.volume" }}|{{ .Driver }}|{{ len .Options }}' "$name" 2>/dev/null)"; then
          if [[ "$identity" != "$SMOKE_PROJECT|$volume|local|0" ]] || ! "${DOCKER[@]}" volume rm "$name"; then
            log "Could not safely remove fixture volume $name"
            status=1
          fi
        fi
      done
    else
      log "Could not stop fixture project $SMOKE_PROJECT"
      status=1
    fi
  fi
  rm -f -- "$scratch/fixture.yaml" "$scratch/smoke-state.json" "$scratch/legacy.dump"
  rmdir -- "$scratch" || status=1
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_healthy() {
  local svc="$1" timeout="${2:-$TIMEOUT}"
  local cid status elapsed=0
  while (( elapsed < timeout )); do
    cid="$("${COMPOSE[@]}" ps -q "$svc" 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$("${DOCKER[@]}" inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo unknown)"
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

log "=== LD-404 Release Smoke & Deployment Verification ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="
log "Smoke project: $SMOKE_PROJECT"

log "1. Verify the rendered Compose targets and volume definitions"
"${COMPOSE[@]}" config --format json | python3 -c '
import json
import sys

model = json.load(sys.stdin)
project = sys.argv[1]
volumes = model["volumes"]
services = model["services"]
def require(condition, message):
    if not condition:
        sys.exit(message)

require(model["name"] == project, "Unexpected Compose project")
require(services["backend"]["environment"].get("ADMIN_USER_AUDIT_RETENTION_DAYS") == "730",
        "Expected Compose audit retention default of 730 days")
for kind, driver in (("volumes", "local"), ("networks", "bridge")):
    for key, resource in model[kind].items():
        require(resource["name"] == f"{project}_{key}" and not resource.get("external")
                and not resource.get("driver_opts") and resource.get("driver", driver) == driver, f"Unexpected {kind} definition: {key}")
for service, db, database, network in (
    ("backend", "backend-db", "cnpm", "backend-network"),
    ("github-integration", "github-db", "github_integration", "github-internal"),
):
    fixture = services[db]
    app = services[service]
    env = app["environment"]
    require(env.get("DB_URL") == f"jdbc:postgresql://{db}:5432/{database}"
            and env.get("DB_USERNAME") == env.get("DB_PASSWORD") == "livingdocs"
            and not any(k.startswith(("SPRING_DATASOURCE_", "SPRING_FLYWAY_")) for k in env),
            f"Unexpected JDBC target for {service}")
    require(network in app["networks"] and set(fixture["networks"]) == {network}
            and not app.get("network_mode") and not fixture.get("network_mode")
            and not app.get("extra_hosts"), f"Unexpected network for {service} or {db}")
    require(not fixture.get("ports") and fixture["image"] == "postgres:16"
            and fixture["environment"] == dict(POSTGRES_DB=database, POSTGRES_USER="livingdocs", POSTGRES_PASSWORD="livingdocs"),
            f"Unexpected fixture config for {db}")
    mounts = fixture["volumes"]
    require(db + "-data" in volumes and len(mounts) == 1 and mounts[0]["type"] == "volume"
            and mounts[0]["source"] == db + "-data" and mounts[0]["target"] == "/var/lib/postgresql/data",
            f"Unexpected data mount for {db}")
' "$SMOKE_PROJECT" || fail "Compose fixture configuration rejected"
pass "Default Compose PostgreSQL credentials, JDBC targets and project-scoped volumes verified"
pass "Compose audit retention default is 730 days without an override"

# Check both labels and names before creating anything. In particular, Compose can
# reuse an existing volume with the expected name even if its labels are missing.
for resource in container volume network; do
  list_args=()
  if [[ "$resource" == container ]]; then list_args+=(--all); fi
  existing="$("${DOCKER[@]}" "$resource" ls "${list_args[@]}" --filter "label=com.docker.compose.project=$SMOKE_PROJECT" --quiet)" ||
    fail "Cannot check existing $resource resources"
  [[ -z "$existing" ]] || fail "Smoke project already owns $resource resources"
done
for resource in volume network; do
  names="$("${DOCKER[@]}" "$resource" ls --format '{{.Name}}')" || fail "Cannot list $resource names"
  if grep -q "^${SMOKE_PROJECT}_" <<< "$names"; then
    fail "A $resource already uses the smoke project name"
  fi
done

owns_project=true
log "2. Start only the two Postgres fixtures"
"${COMPOSE[@]}" up -d --no-deps --no-build backend-db github-db

verify_fixture() {
  local service="$1" database="$2" cid actual volume="${SMOKE_PROJECT}_${1}-data"
  wait_healthy "$service" 120 || fail "$service did not become healthy"
  cid="$("${COMPOSE[@]}" ps -q "$service")"
  actual="$("${DOCKER[@]}" inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}|{{ index .Config.Labels "com.docker.compose.service" }}|{{ range .Mounts }}{{ .Type }}:{{ .Name }}:{{ .Destination }}:{{ .RW }}{{ end }}' "$cid")"
  [[ "$actual" == "$SMOKE_PROJECT|$service|volume:$volume:/var/lib/postgresql/data:true" ]] ||
    fail "Unexpected container identity or data mount for $service"
  actual="$("${DOCKER[@]}" volume inspect -f '{{ index .Labels "com.docker.compose.project" }}|{{ index .Labels "com.docker.compose.volume" }}|{{ .Driver }}|{{ .Scope }}|{{ len .Options }}' "$volume")"
  [[ "$actual" == "$SMOKE_PROJECT|$service-data|local|local|0" ]] ||
    fail "Unexpected volume identity for $service"
  actual="$("${COMPOSE[@]}" exec -T -e PGPASSWORD=livingdocs "$service" psql -X -w -h "$service" -U livingdocs -d "$database" -v ON_ERROR_STOP=1 -Atc 'SELECT current_database(), current_user')"
  [[ "$actual" == "$database|livingdocs" ]] || fail "Unexpected SQL identity for $service"
  pass "$service uses $volume and authenticated as livingdocs on $database"
}
verify_fixture backend-db cnpm
verify_fixture github-db github_integration

check_restored_data() {
  local value
  value="$("${COMPOSE[@]}" exec -T -e PGPASSWORD=livingdocs backend-db psql -X -h backend-db \
    -U livingdocs -d cnpm -v ON_ERROR_STOP=1 -Atc \
    "SELECT payload || '|' || pg_get_userbyid(relowner) FROM upgrade_probe.records, pg_class WHERE oid = 'upgrade_probe.records'::regclass")"
  [[ "$value" == "legacy PostgreSQL data|livingdocs" ]] || fail "Restored data or owner differs"
  value="$("${COMPOSE[@]}" exec -T -e PGPASSWORD=livingdocs backend-db psql -X -h backend-db \
    -U livingdocs -d cnpm -v ON_ERROR_STOP=1 -Atc \
    "SELECT setting_value FROM public.system_settings WHERE setting_key = 'retention.auditLogDays'")"
  [[ "$value" == 0 ]] || fail "Restored audit policy differs"
}

if [[ "${VERIFY_LEGACY_RESTORE:-0}" == 1 ]]; then
  log "Rehearsing legacy PostgreSQL backup and restore"
  legacy="$SMOKE_PROJECT-legacy"
  "${DOCKER[@]}" run -d --rm --name "$legacy" --network none \
    --label "com.docker.compose.project=$SMOKE_PROJECT" \
    --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_DB=cnpm -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:16
  legacy_started=true
  for (( attempt=0; attempt<60; attempt++ )); do
    if "${DOCKER[@]}" exec -e PGPASSWORD=postgres "$legacy" \
      psql -X -h 127.0.0.1 -U postgres -d cnpm -Atc 'SELECT 1' >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  "${DOCKER[@]}" exec -e PGPASSWORD=postgres "$legacy" \
    psql -X -h 127.0.0.1 -U postgres -d cnpm -v ON_ERROR_STOP=1 \
    -c "CREATE SCHEMA upgrade_probe;
        CREATE TABLE upgrade_probe.records (id bigserial PRIMARY KEY, payload text NOT NULL);
        CREATE TABLE public.system_settings (setting_key varchar(100) PRIMARY KEY, setting_value varchar(4000) NOT NULL,
            updated_at timestamptz NOT NULL, updated_by varchar(255));
        INSERT INTO public.system_settings VALUES ('retention.auditLogDays', '0', now(), 'legacy-fixture');
        INSERT INTO upgrade_probe.records (payload) VALUES ('legacy PostgreSQL data');"
  "${DOCKER[@]}" exec -e PGPASSWORD=postgres "$legacy" \
    pg_dump -h 127.0.0.1 -U postgres -d cnpm -Fc > "$scratch/legacy.dump"
  "${COMPOSE[@]}" exec -T -e PGPASSWORD=livingdocs backend-db \
    pg_restore -h backend-db -U livingdocs -d cnpm --no-owner --no-acl --single-transaction \
    < "$scratch/legacy.dump"
  check_restored_data
  "${COMPOSE[@]}" exec -T -e PGPASSWORD=livingdocs backend-db psql -X -h backend-db \
    -U livingdocs -d cnpm -v ON_ERROR_STOP=1 -c \
    "BEGIN; INSERT INTO upgrade_probe.records (payload) VALUES ('write probe'); ROLLBACK;"
  if "${COMPOSE[@]}" exec -T -e PGPASSWORD=incorrect backend-db psql -X -h backend-db \
    -U livingdocs -d cnpm -w -Atc 'SELECT 1'; then
    fail "Restored database accepted an incorrect password"
  fi
  pass "Legacy data restored with working TCP authentication, ownership and writes"
fi

log "3. Build and start applications against the verified fixtures"
if ! "${COMPOSE[@]}" up "$build_option" -d --no-recreate; then
  "${COMPOSE[@]}" ps --all || true
  "${COMPOSE[@]}" logs --no-color --tail 120 backend github-integration >> "$REPORT_FILE" 2>&1 || true
  tail -n 120 "$REPORT_FILE"
  fail "Application startup failed"
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
if [[ "${VERIFY_LEGACY_RESTORE:-0}" == 1 ]]; then
  check_restored_data
  pass "Restored legacy data survived the stack restart"
fi

log "8. Running post-restart E2E persistence smoke"
python3 scripts/release_smoke_test.py \
  --phase post-restart \
  --state-file "$SMOKE_STATE_FILE" \
  --report-file "$REPORT_DIR/smoke-post-restart-result.json" \
  || fail "post-restart smoke failed"
pass "post-restart smoke passed"

log "=== LD-404 smoke & deployment verification complete ==="
log "Report: ${REPORT_FILE}"
