#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# reset-env.ps1: delete the local environments and rebuild them from the lockfiles.
# Parity: reset-env.sh (documents the scope). .env is kept.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/reset-env.ps1 [--yes] [--keep-db] [--ci] [-h|--help] [-- setup flags]

  --yes       Do not ask for confirmation
  --keep-db   Keep artifacts/app.db (the local SQLite database)
  --ci        Plain output (no colours); implies --yes
  -- ...      Everything after -- is passed to scripts/setup.ps1 (e.g. -- --skip-playwright)
'@ | Write-Host
}

$yes = $false; $keepDb = $false; $setupArgs = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}yes$' { $yes = $true; break }
        '^-{1,2}keep-db$' { $keepDb = $true; break }
        '^-{1,2}ci$' { $env:NO_COLOR = '1'; $yes = $true; $setupArgs += '--ci'; break }
        '^--$' { if ($i + 1 -lt $args.Count) { $setupArgs += $args[($i + 1)..($args.Count - 1)] }; $i = $args.Count; break }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}

$root = Get-RepoRoot
if (-not $yes) {
    $answer = Read-Host "Delete .venv, node_modules and artifacts/$(if ($keepDb) { ' (keeping app.db)' }) and reinstall? [y/N]"
    if ($answer -notmatch '^[Yy]$') { Write-Info 'cancelled'; exit 0 }
}

Write-Step 'Removing local environments'
$db = Join-Path $root 'artifacts/app.db'
$dbBackup = $null
if ($keepDb -and (Test-Path $db)) { $dbBackup = [IO.Path]::GetTempFileName(); Copy-Item $db $dbBackup -Force }
foreach ($t in @((Join-Path (Get-BackendDir) '.venv'), (Join-Path (Get-FrontendDir) 'node_modules'), (Join-Path (Get-E2eDir) 'node_modules'))) {
    if (Test-Path $t) { Remove-Item -Recurse -Force $t; Write-Info "deleted $([IO.Path]::GetRelativePath($root, $t))" }
}
$pwsh = (Get-Process -Id $PID).Path
& $pwsh -NoProfile -File (Join-Path $PSScriptRoot 'clean.ps1') --all | Out-Null
if ($dbBackup) {
    New-Item -ItemType Directory -Force -Path (Split-Path $db) | Out-Null
    Move-Item $dbBackup $db -Force
    Write-Info 'kept artifacts/app.db'
}

Write-Step 'Reinstalling (scripts/setup.ps1)'
& $pwsh -NoProfile -File (Join-Path $PSScriptRoot 'setup.ps1') @setupArgs
exit $LASTEXITCODE
