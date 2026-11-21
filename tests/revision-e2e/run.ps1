param(
    [string]$LogPath = (Join-Path $PWD 'revision-e2e.log'),
    [switch]$Restart
)

$project = 'livingdocs-revision-' + [Guid]::NewGuid().ToString('N')
$compose = @('compose', '-p', $project, '-f', (Join-Path $PSScriptRoot 'compose.yaml'))
try {
    if ($Restart) {
        & docker @compose up --build --detach --wait postgres ai 2>&1 | Tee-Object -FilePath $LogPath
        $testExit = $LASTEXITCODE
        if ($testExit -eq 0) {
            & docker @compose run --rm -e LIVINGDOCS_E2E_RESTART_PHASE=stage test 2>&1 |
                Tee-Object -FilePath $LogPath -Append
            $testExit = $LASTEXITCODE
        }
        if ($testExit -eq 0) {
            & docker @compose up --detach --wait --force-recreate --no-deps ai 2>&1 |
                Tee-Object -FilePath $LogPath -Append
            $testExit = $LASTEXITCODE
        }
        if ($testExit -eq 0) {
            & docker @compose run --rm -e LIVINGDOCS_E2E_RESTART_PHASE=resume test 2>&1 |
                Tee-Object -FilePath $LogPath -Append
            $testExit = $LASTEXITCODE
        }
        & docker @compose logs --no-color postgres ai 2>&1 | Tee-Object -FilePath $LogPath -Append
    } else {
        & docker @compose up --build --abort-on-container-exit --exit-code-from test 2>&1 |
            Tee-Object -FilePath $LogPath
        $testExit = $LASTEXITCODE
    }
} finally {
    & docker @compose down --volumes 2>&1 | Tee-Object -FilePath $LogPath -Append
}
exit $testExit
