#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# db-migrate.ps1: apply Alembic migrations to DATABASE_URL (Phase 5). Parity: db-migrate.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/db-migrate.ps1 [--revision REV] [--downgrade REV] [--current] [-h|--help]

  (no option)          Upgrade to the latest revision (head)
  --revision REV       Upgrade to REV instead of head
  --downgrade REV      Downgrade to REV (e.g. -1 or base). Refused in production.
  --current            Show the database revision; exit 1 if it is not at head

DATABASE_URL comes from the environment or .env (see .env.example).
'@ | Write-Host
}

$cmd = @('upgrade')
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}revision$' { $cmd = @('upgrade', '--revision', $args[++$i]) }
        '^-{1,2}downgrade$' { $cmd = @('downgrade', $args[++$i]) }
        '^-{1,2}current$' { $cmd = @('current') }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
Import-DotEnv
$backend = Get-BackendDir
Write-Step "Database migrations: $($cmd -join ' ')"
if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', 'scripts/db.py') + $cmd))) { exit 1 }
