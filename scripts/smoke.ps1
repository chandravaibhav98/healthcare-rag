#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# smoke.ps1: probe a running API (health, readiness, both /qa paths, schema, latency).
# Parity: smoke.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/smoke.ps1 [--base-url URL] [--bench N] [-h|--help]

  --base-url URL  API base URL (default: http://API_HOST:API_PORT from .env)
  --bench N       Send N extra /qa requests and check p95 <= 150 ms
'@ | Write-Host
}

Import-DotEnv
$apiHost = if ($env:API_HOST) { $env:API_HOST } else { '127.0.0.1' }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { '8000' }
$baseUrl = "http://${apiHost}:${apiPort}"; $extra = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}base-url$' { $baseUrl = $args[++$i] }
        '^-{1,2}bench$' { $extra += @('--bench', $args[++$i]) }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
Write-Step "Smoke test $baseUrl"
if (-not (Invoke-Native uv (@('run', '--directory', (Get-BackendDir), 'python', 'scripts/smoke.py', '--base-url', $baseUrl) + $extra))) { exit 1 }
