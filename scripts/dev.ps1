#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# dev.ps1: run the API (uvicorn --reload) and the web app (Vite) together.
# Ctrl+C stops both. Parity: dev.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/dev.ps1 [--api-only | --web-only] [-h|--help]

  --api-only   Run only the FastAPI service (http://API_HOST:API_PORT)
  --web-only   Run only the Vite dev server (http://localhost:5173)
'@ | Write-Host
}

Assert-KnownFlags $args @('api-only', 'web-only', 'h', 'help') { Show-Usage }
if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
$api = -not (Test-Flag $args 'web-only'); $web = -not (Test-Flag $args 'api-only')
if (-not ($api -or $web)) { Stop-Script '--api-only and --web-only are mutually exclusive' }

Import-DotEnv
$root = Get-RepoRoot
$apiHost = if ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { '8000' }
$index = if ($env:INDEX_DIR) { $env:INDEX_DIR } else { 'artifacts/index' }
if (-not [System.IO.Path]::IsPathRooted($index)) { $index = Join-Path $root $index }

$procs = @()
try {
    if ($api) {
        Assert-Command uv 'Run scripts/setup.ps1 first.'
        if (-not (Test-Path (Join-Path $index 'manifest.json'))) { Stop-Script "No index at $index. Run scripts/build-index.ps1 first." }
        Write-Step "API on http://${apiHost}:${apiPort} (docs at /docs)"
        $procs += Start-Process uv -NoNewWindow -PassThru -ArgumentList @(
            'run', '--directory', (Get-BackendDir), 'uvicorn', '--factory', 'app.main:create_app',
            '--reload', '--host', $apiHost, '--port', $apiPort)
    }
    if ($web) {
        Assert-Command npm 'Install Node (see scripts/preflight.ps1).'
        Write-Step 'Web on http://localhost:5173'
        $npm = if ($IsWindows) { 'npm.cmd' } else { 'npm' }
        $procs += Start-Process $npm -NoNewWindow -PassThru -ArgumentList @('--prefix', (Join-Path $root 'frontend'), 'run', 'dev')
    }
    # Return as soon as either process exits (or on Ctrl+C), then stop the other one.
    while (-not ($procs | Where-Object HasExited)) { Start-Sleep -Milliseconds 500 }
}
finally {
    foreach ($p in $procs) {
        if ($p.HasExited) { continue }
        # uvicorn --reload and npm spawn children: stop the whole tree so ports are freed.
        if ($IsWindows) { & taskkill /T /F /PID $p.Id *> $null }
        else { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
