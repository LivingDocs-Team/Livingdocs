param(
    [switch]$Clean,
    [switch]$NoUp,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

if ($NoUp) {
    throw "LD-404 requires fresh fixtures. Remove -NoUp."
}

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    throw "Run scripts/verify-compose.sh from Linux or WSL with Docker Compose available."
}

$repo = Split-Path -Parent $PSScriptRoot
$smokeArgs = @()
if ($Clean) {
    $smokeArgs += "--clean"
}

# Run the same fixture checks as CI. Do not start or tear down a Compose stack here.
& $wsl.Source --cd $repo --exec env "VERIFY_TIMEOUT=$TimeoutSeconds" bash ./scripts/verify-compose.sh @smokeArgs
exit $LASTEXITCODE
