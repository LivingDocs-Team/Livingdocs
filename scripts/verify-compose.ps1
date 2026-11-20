param(
    [switch]$Clean,
    [switch]$NoUp,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# === P1 FIX: Dùng project name riêng cho smoke test ===
$SmokeProject = $env:SMOKE_PROJECT
if (-not $SmokeProject) { $SmokeProject = "livingdocs-smoke" }
$ComposeCmd = @("compose", "-p", $SmokeProject, "-f", "compose.yaml")

# === P1 FIX: Ánh xạ cổng riêng ===
$env:BACKEND_DB_PORT           = $env:SMOKE_BACKEND_DB_PORT           ?? "5444"
$env:GITHUB_DB_PORT            = $env:SMOKE_GITHUB_DB_PORT            ?? "5443"
$env:BACKEND_PORT              = $env:SMOKE_BACKEND_PORT              ?? "8081"
$env:FRONTEND_PORT             = $env:SMOKE_FRONTEND_PORT             ?? "3001"
$env:AI_SERVICE_PORT           = $env:SMOKE_AI_SERVICE_PORT           ?? "8002"
$env:ANALYZER_PORT             = $env:SMOKE_ANALYZER_PORT             ?? "8003"
$env:GITHUB_INTEGRATION_PORT   = $env:SMOKE_GITHUB_INTEGRATION_PORT   ?? "8083"

$env:FRONTEND_URL              = "http://localhost:$env:FRONTEND_PORT"
$env:BACKEND_URL               = "http://localhost:$env:BACKEND_PORT"
$env:ANALYZER_URL              = "http://localhost:$env:ANALYZER_PORT"
$env:AI_SERVICE_URL            = "http://localhost:$env:AI_SERVICE_PORT"
$env:GITHUB_INTEGRATION_URL    = "http://localhost:$env:GITHUB_INTEGRATION_PORT"

$ReportDir = "artifacts"
$ReportFile = Join-Path $ReportDir "ld-404-smoke-report.log"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
Set-Content -Path $ReportFile -Value "" -Encoding UTF8

# === P2 FIX: State file nằm trong thư mục tạm ===
$SmokeStateDir = $env:SMOKE_STATE_DIR
if (-not $SmokeStateDir) {
    $SmokeStateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("ld404-smoke-state-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $SmokeStateDir -Force | Out-Null
}
# Trên Windows, giới hạn quyền cho user hiện tại
$acl = Get-Acl $SmokeStateDir
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
    "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($rule)
Set-Acl $SmokeStateDir $acl

$env:SMOKE_STATE_FILE = $env:SMOKE_STATE_FILE
if (-not $env:SMOKE_STATE_FILE) {
    $env:SMOKE_STATE_FILE = Join-Path $SmokeStateDir "smoke-state.json"
}

function Write-Log([string]$Msg) {
    Write-Host $Msg
    Add-Content -Path $ReportFile -Value $Msg -Encoding UTF8
}
function Pass([string]$Msg) { Write-Log " [PASS] $Msg" }
function Fail([string]$Msg) { Write-Log " [FAIL] $Msg"; exit 1 }

# Load .env
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

function Wait-AllHealthy {
    $services = @("backend-db","github-db","code-analyzer","ai-service","github-integration","backend","frontend")
    foreach ($svc in $services) {
        $elapsed = 0; $ok = $false
        while ($elapsed -lt $TimeoutSeconds) {
            $cid = (& docker @ComposeCmd ps -q $svc 2>$null)
            if ($cid) {
                $status = (& docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $cid)
                if ($status -eq "healthy" -or $status -eq "running") { $ok = $true; break }
            }
            Start-Sleep -Seconds 3
            $elapsed += 3
        }
        if ($ok) { Pass "$svc is healthy/running" } else { Fail "$svc did not become healthy within ${TimeoutSeconds}s" }
    }
}

Write-Log "=== LD-404 Release Smoke & Deployment Verification ($(Get-Date -Format o)) ==="
Write-Log "Smoke project: $SmokeProject"
Write-Log "State file (secure, tmp): $env:SMOKE_STATE_FILE"

Write-Log "1. Validate compose configuration"
& docker @ComposeCmd config --quiet
if ($LASTEXITCODE -ne 0) { Fail "compose.yaml is invalid" }
Pass "compose.yaml is valid"

# === P1 FIX: Chỉ xóa volume trong project smoke ===
if ($Clean) {
    Write-Log "2. Clean deployment: tearing down smoke project (project: $SmokeProject)"
    & docker @ComposeCmd down -v --remove-orphans
    Pass "Removed old smoke project containers and volumes (project: $SmokeProject)"
}

if (-not $NoUp) {
    Write-Log "3. Starting stack with docker compose up --build -d (project: $SmokeProject)"
    & docker @ComposeCmd up --build -d
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }
}

Write-Log "4. Waiting for all services to become healthy"
Wait-AllHealthy

Write-Log "5. Verifying database migrations"
$flywayOk = (& docker @ComposeCmd exec -T github-db psql -U livingdocs -d github_integration -tAc "SELECT COUNT(*) FROM flyway_schema_history WHERE success = true;").Trim()
if ([int]$flywayOk -gt 0) { Pass "github-db Flyway migrations applied ($flywayOk successful versions)" }
else { Fail "github-db Flyway migrations failed" }

$flywayFail = (& docker @ComposeCmd exec -T github-db psql -U livingdocs -d github_integration -tAc "SELECT COUNT(*) FROM flyway_schema_history WHERE success = false;").Trim()
if ([int]$flywayFail -eq 0) { Pass "github-db Flyway migrations have no failed versions" }
else { Fail "github-db Flyway migrations contain failed versions" }

Write-Log "6. Running pre-restart E2E smoke"
python scripts/release_smoke_test.py `
    --phase pre-restart `
    --state-file $env:SMOKE_STATE_FILE `
    --report-file (Join-Path $ReportDir "smoke-pre-restart-result.json")
if ($LASTEXITCODE -ne 0) { Fail "pre-restart smoke failed" }
Pass "pre-restart smoke passed"

Write-Log "7. Restarting services (simulating redeploy)"
& docker @ComposeCmd restart
Wait-AllHealthy
Pass "All services healthy after restart"

Write-Log "8. Running post-restart E2E persistence smoke"
python scripts/release_smoke_test.py `
    --phase post-restart `
    --state-file $env:SMOKE_STATE_FILE `
    --report-file (Join-Path $ReportDir "smoke-post-restart-result.json")
if ($LASTEXITCODE -ne 0) { Fail "post-restart smoke failed" }
Pass "post-restart smoke passed"

# Cleanup
if (Test-Path $env:SMOKE_STATE_FILE) { Remove-Item $env:SMOKE_STATE_FILE -Force }
if (Test-Path $SmokeStateDir) { Remove-Item $SmokeStateDir -Recurse -Force }

Write-Log "=== LD-404 smoke & deployment verification complete ==="
Write-Log "Report: $ReportFile"