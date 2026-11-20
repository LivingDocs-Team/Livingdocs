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

# Guard: không cho --Clean nếu SMOKE_PROJECT trùng stack chính
$MainProject = $env:MAIN_PROJECT
if (-not $MainProject) { $MainProject = "livingdocs" }
if ($Clean -and ($SmokeProject -eq $MainProject -or $SmokeProject -eq "default" -or $SmokeProject -eq "livingdocs")) {
    Write-Host " [FAIL] Refusing to --Clean: SMOKE_PROJECT '$SmokeProject' looks like the main stack."
    exit 1
}

$ComposeCmd = @("compose", "-p", $SmokeProject, "-f", "compose.yaml")

# === FIX: Load .env TRƯỚC khi set port ===
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.*)\s*$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

# === Helper: set env CHỈ KHI chưa có giá trị ===
function Set-DefaultEnv([string]$Name, [string]$Value) {
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

# === FIX: Default Env & Secrets ===
Set-DefaultEnv "TOKEN_ENCRYPTION_KEY" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
Set-DefaultEnv "GITHUB_INTEGRATION_INTERNAL_SECRET" "smoke-test-internal-secret"
Set-DefaultEnv "INTERNAL_API_SECRET" "dummy-secret-123"
Set-DefaultEnv "AI_SERVICE_INTERNAL_SECRET" $env:INTERNAL_API_SECRET

$ReportDir = "artifacts"
$ReportFile = Join-Path $ReportDir "ld-404-smoke-report.log"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
Set-Content -Path $ReportFile -Value "" -Encoding UTF8

# === P2 FIX: State file bảo mật (thư mục tạm, quyền 700) ===
$SmokeStateDir = $env:SMOKE_STATE_DIR
if (-not $SmokeStateDir) {
    $SmokeStateDir = Join-Path ([System.IO.Path]::GetTempPath()) ("ld404-smoke-state-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $SmokeStateDir -Force | Out-Null
}
$acl = Get-Acl $SmokeStateDir
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
    "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($rule)
Set-Acl $SmokeStateDir $acl

if (-not $env:SMOKE_STATE_FILE) {
    $env:SMOKE_STATE_FILE = Join-Path $SmokeStateDir "smoke-state.json"
}

function Write-Log([string]$Msg) {
    Write-Host $Msg
    Add-Content -Path $ReportFile -Value $Msg -Encoding UTF8
}
function Pass([string]$Msg) { Write-Log " [PASS] $Msg" }
function Fail([string]$Msg) { Write-Log " [FAIL] $Msg"; exit 1 }

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

# === FIX: Đọc port THỰC TẾ từ Docker ===
function Resolve-SmokeEndpoint {
    param([string]$Service, [int]$ContainerPort)
    $raw = (& docker @ComposeCmd port $Service $ContainerPort 2>$null)
    if (-not $raw) {
        throw "Service '$Service' chưa publish container port $ContainerPort. Kiểm tra 'docker compose -p $SmokeProject ps'."
    }
    $line = ($raw -split "`n")[0].Trim()
    return [int](($line -split ':')[-1].Trim())
}

Write-Log "=== LD-404 Release Smoke & Deployment Verification ($(Get-Date -Format o)) ==="
Write-Log "Smoke project: $SmokeProject"
Write-Log "State file (secure, tmp): $env:SMOKE_STATE_FILE"

Write-Log "1. Validate compose configuration"
& docker @ComposeCmd config --quiet
if ($LASTEXITCODE -ne 0) { Fail "compose.yaml is invalid" }
Pass "compose.yaml is valid"

if ($Clean) {
    Write-Log "2. Clean deployment: tearing down smoke project (project: $SmokeProject)"
    & docker @ComposeCmd down -v --remove-orphans
    if ($LASTEXITCODE -ne 0) { Fail "docker compose down failed" }
    Pass "Removed old smoke project containers and volumes (project: $SmokeProject)"
}

if (-not $NoUp) {
    Write-Log "3. Starting stack with docker compose up --build -d (project: $SmokeProject)"
    & docker @ComposeCmd up --build -d
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }
}

Write-Log "4. Waiting for all services to become healthy"
Wait-AllHealthy

# === FIX: Resolve port thực tế từ Docker ===
Write-Log "4b. Resolving smoke endpoints from docker"
try {
    $BackendHostPort   = Resolve-SmokeEndpoint -Service "backend"            -ContainerPort 8080
    $FrontendHostPort  = Resolve-SmokeEndpoint -Service "frontend"           -ContainerPort 80
    $AiServiceHostPort = Resolve-SmokeEndpoint -Service "ai-service"         -ContainerPort 8001
    $AnalyzerHostPort  = Resolve-SmokeEndpoint -Service "code-analyzer"      -ContainerPort 8000
    $GithubIntHostPort = Resolve-SmokeEndpoint -Service "github-integration" -ContainerPort 8082
} catch {
    Fail $_.Exception.Message
}

$env:BACKEND_URL            = "http://localhost:$BackendHostPort"
$env:FRONTEND_URL           = "http://localhost:$FrontendHostPort"
$env:AI_SERVICE_URL         = "http://localhost:$AiServiceHostPort"
$env:ANALYZER_URL           = "http://localhost:$AnalyzerHostPort"
$env:GITHUB_INTEGRATION_URL = "http://localhost:$GithubIntHostPort"

Write-Log "     backend            = $env:BACKEND_URL"
Write-Log "     frontend           = $env:FRONTEND_URL"
Write-Log "     ai-service         = $env:AI_SERVICE_URL"
Write-Log "     code-analyzer      = $env:ANALYZER_URL"
Write-Log "     github-integration = $env:GITHUB_INTEGRATION_URL"
Pass "Smoke endpoints resolved"

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
if ($LASTEXITCODE -ne 0) { Fail "docker compose restart failed" }
Wait-AllHealthy
Pass "All services healthy after restart"

Write-Log "8. Running post-restart E2E persistence smoke"
python scripts/release_smoke_test.py `
    --phase post-restart `
    --state-file $env:SMOKE_STATE_FILE `
    --report-file (Join-Path $ReportDir "smoke-post-restart-result.json")
if ($LASTEXITCODE -ne 0) { Fail "post-restart smoke failed" }
Pass "post-restart smoke passed"

# Cleanup state (P2: không để password tồn tại sau khi chạy)
if (Test-Path $env:SMOKE_STATE_FILE) { Remove-Item $env:SMOKE_STATE_FILE -Force }
if (Test-Path $SmokeStateDir) { Remove-Item $SmokeStateDir -Recurse -Force }

Write-Log "=== LD-404 smoke & deployment verification complete ==="
Write-Log "Report: $ReportFile"