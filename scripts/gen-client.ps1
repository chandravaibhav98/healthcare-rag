#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# gen-client.ps1: OpenAPI snapshot → frontend TypeScript API types (Phase 6).
# Parity: gen-client.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/gen-client.ps1 [--check] [-h|--help]

  --check   Fail if backend/openapi.json or the generated TS types are stale (CI)
'@ | Write-Host
}

$check = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}check$' { $check = $true }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
Assert-Command npm 'Run scripts/setup.ps1 first.'
$backend = Get-BackendDir
$frontend = Get-FrontendDir
if ($check) {
    Write-Step 'Contract snapshots and API types are current'
    if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/export_schemas.py', '--check'))) { exit 1 }
    if (-not (Invoke-Native npm @('--prefix', $frontend, 'run', '-s', 'gen:api:check'))) { exit 1 }
} else {
    Write-Step 'Export backend/openapi.json'
    if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/export_schemas.py'))) { exit 1 }
    Write-Step 'Generate frontend/src/api/generated/schema.d.ts'
    if (-not (Invoke-Native npm @('--prefix', $frontend, 'run', '-s', 'gen:api'))) { exit 1 }
}
