param(
    [switch]$Clean,
    [switch]$NoUp,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$ComposeCmd = @("compose", "-f", "compose.yaml")
$ReportDir = "artifacts"
$ReportFile = Join-Path $ReportDir "ld-404-smoke-report.log"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
Set-Content -Path $ReportFile -Value "" -Encoding UTF8

function Write-Log([string]$Msg) {
    Write-Host $Msg
    Add-Content -Path $ReportFile -Value $Msg -Encoding UTF8
}
function Pass([string]$Msg) { Write-Log "  [PASS] $Msg" }
function Fail([string]$Msg) { Write-Log "  [FAIL] $Msg"; exit 1 }

# Nap bien tu file .env vao moi truong hien tai cho Python script
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

function Wait-AllHealthy {
    $services = @("backend-db", "github-db", "code-analyzer", "ai-service", "github-integration", "backend", "frontend")
    foreach ($svc in $services) {
        $elapsed = 0
        $ok = $false
        while ($elapsed -lt $TimeoutSeconds) {
            $cid = (& docker @ComposeCmd ps -q $svc 2>$null)
            if ($cid) {
                $status = (& docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $cid)
                if ($status -eq "healthy" -or $status -eq "running") {
                    $ok = $true
                    break
                }
            }
            Start-Sleep -Seconds 3
            $elapsed += 3
        }
        if ($ok) { Pass "$svc is healthy/running" } else { Fail "$svc did not become healthy within ${TimeoutSeconds}s" }
    }
}

Write-Log "=== LD-404 Release Smoke & Deployment Verification ($(Get-Date -Format o)) ==="

Write-Log "1. Validate compose configuration"
& docker @ComposeCmd config --quiet
if ($LASTEXITCODE -ne 0) { Fail "compose.yaml is invalid" }
Pass "compose.yaml is valid"

if ($Clean) {
    Write-Log "2. Clean deployment: tearing down existing containers & volumes"
    & docker @ComposeCmd down -v --remove-orphans
    Pass "Removed old containers and volumes"
}

if (-not $NoUp) {
    Write-Log "3. Starting stack with docker compose up --build -d"
    & docker @ComposeCmd up --build -d
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }
}

Write-Log "4. Waiting for all services to become healthy"
Wait-AllHealthy

Write-Log "5. Verifying database migrations"
$flywayOk = (& docker @ComposeCmd exec -T github-db psql -U livingdocs -d github_integration -tAc "SELECT COUNT(*) FROM flyway_schema_history WHERE success = true;").Trim()
if ([int]$flywayOk -gt 0) { Pass "github-db Flyway migrations applied ($flywayOk successful versions)" } else { Fail "github-db Flyway migrations failed" }

$flywayFail = (& docker @ComposeCmd exec -T github-db psql -U livingdocs -d github_integration -tAc "SELECT COUNT(*) FROM flyway_schema_history WHERE success = false;").Trim()
if ([int]$flywayFail -eq 0) { Pass "github-db has 0 failed Flyway migrations" } else { Fail "github-db has failed Flyway migrations" }

$backendTables = (& docker @ComposeCmd exec -T backend-db psql -U livingdocs -d cnpm -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';").Trim()
if ([int]$backendTables -gt 0) { Pass "backend-db schema initialized ($backendTables tables in cnpm)" } else { Fail "backend-db schema has no tables" }

Write-Log "6. Verifying service health endpoints"
Invoke-RestMethod -Uri "http://localhost:8000/health" | Out-Null; Pass "code-analyzer /health (:8000)"
Invoke-RestMethod -Uri "http://localhost:8001/health" | Out-Null; Pass "ai-service /health (:8001)"
& docker @ComposeCmd exec -T github-integration curl -fsS http://localhost:8082/actuator/health | Out-Null; Pass "github-integration /actuator/health (:8082)"
Invoke-RestMethod -Uri "http://localhost:8080/actuator/health" | Out-Null; Pass "backend /actuator/health (:8080)"
Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing | Out-Null; Pass "frontend serves / (:3000)"

Write-Log "7. Running Pre-Restart E2E Smoke Test (Generation & Review)"
$preOut = & python scripts/release_smoke_test.py --phase pre-restart --state-file "$ReportDir/smoke-state.json" --report-file "$ReportDir/smoke-e2e-results.json"
$preOut | ForEach-Object { Write-Log $_ }
if ($LASTEXITCODE -ne 0) { Fail "Pre-restart E2E smoke test failed" }

Write-Log "8. Restarting application services for recovery verification"
& docker @ComposeCmd restart code-analyzer ai-service github-integration backend frontend
Wait-AllHealthy

Write-Log "9. Running Post-Restart Persistence Verification"
$postOut = & python scripts/release_smoke_test.py --phase post-restart --state-file "$ReportDir/smoke-state.json" --report-file "$ReportDir/smoke-e2e-results.json"
$postOut | ForEach-Object { Write-Log $_ }
if ($LASTEXITCODE -ne 0) { Fail "Post-restart persistence verification failed" }

Write-Log "=== ALL LD-404 RELEASE SMOKE & PERSISTENCE CHECKS PASSED ==="
Write-Log "Recorded results saved to: $ReportFile"