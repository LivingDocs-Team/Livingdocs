param([string]$LogPath = (Join-Path $PWD 'revision-e2e.log'))

$project = 'livingdocs-revision-' + [Guid]::NewGuid().ToString('N')
$compose = @('compose', '-p', $project, '-f', (Join-Path $PSScriptRoot 'compose.yaml'))
try {
    & docker @compose up --build --abort-on-container-exit --exit-code-from test 2>&1 |
        Tee-Object -FilePath $LogPath
    $testExit = $LASTEXITCODE
} finally {
    & docker @compose down --volumes 2>&1 | Tee-Object -FilePath $LogPath -Append
}
exit $testExit
