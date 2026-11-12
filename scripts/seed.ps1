#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# seed.ps1: admin account and optional demo data (Phase 5). Parity: seed.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/seed.ps1 [--demo] [--reset] [--reset-password] [-h|--help]

  --demo             Also create reviewer@/user@ accounts and demo history (not in production)
  --reset            Empty the application tables first (not in production)
  --reset-password   Reset seeded accounts' passwords to SEED_ADMIN_PASSWORD

Accounts use the domain of SEED_ADMIN_EMAIL and the password SEED_ADMIN_PASSWORD.
'@ | Write-Host
}

$extra = @(); $demo = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}demo$' { $extra += '--demo'; $demo = $true }
        '^-{1,2}(reset|reset-password)$' { $extra += @('--' + ($args[$i] -replace '^-{1,2}', '')) }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
Import-DotEnv
$backend = Get-BackendDir
$index = if ($env:INDEX_DIR) { $env:INDEX_DIR } else { 'artifacts/index' }
if (-not [System.IO.Path]::IsPathRooted($index)) { $index = Join-Path (Get-RepoRoot) $index }

Write-Step 'Migrate'
if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/db.py', 'upgrade'))) { exit 1 }
if ($demo -and -not (Test-Path (Join-Path $index 'manifest.json'))) {
    Write-Step 'Build index (demo answers need it)'
    if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/pipeline.py', 'build'))) { exit 1 }
}
Write-Step 'Seed'
if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', 'scripts/seed.py') + $extra))) { exit 1 }
