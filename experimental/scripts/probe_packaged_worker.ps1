$ErrorActionPreference = "Stop"

$exe = Join-Path $PSScriptRoot "..\apps\desktop\dist-worker\millikan-experimental-worker.exe"
if (-not (Test-Path $exe)) {
    throw "packaged worker not found: $exe"
}

$runDir = Join-Path $env:RUNNER_TEMP "empty_run"
New-Item -ItemType Directory -Force $runDir | Out-Null

$payload = @{
    id = "probe"
    op = "analysis.validate"
    payload = @{ run_dir = $runDir }
} | ConvertTo-Json -Depth 5 -Compress

$text = ($payload | & $exe | Out-String)
Write-Host $text

if ($text -notmatch '"type":"result"') {
    throw "packaged worker could not resolve configs/default.yaml"
}
