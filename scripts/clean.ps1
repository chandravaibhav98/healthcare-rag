#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# clean.ps1: remove build outputs and reports. Parity: clean.sh (documents the scope).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/clean.ps1 [--all] [--dry-run] [--ci] [-h|--help]

  --all       Also delete artifacts/ (index, local database, videos, bundles) and caches
  --dry-run   List what would be deleted
  --ci        Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('all', 'dry-run', 'ci') ${function:Show-Usage}
if (Test-Flag $args 'ci') { $env:NO_COLOR = '1' }
$all = Test-Flag $args 'all'
$dry = Test-Flag $args 'dry-run'
$root = Get-RepoRoot; $backend = Get-BackendDir; $frontend = Get-FrontendDir; $e2e = Get-E2eDir

$targets = @(
    "$backend/evaluation/reports", "$backend/coverage.xml", "$backend/coverage.json", "$backend/.coverage", "$backend/htmlcov",
    "$frontend/dist", "$frontend/coverage", "$e2e/test-results", "$e2e/playwright-report",
    "$root/artifacts/e2e", "$root/artifacts/load", "$root/artifacts/k8s-verify", "$root/artifacts/demo/run"
)
if ($all) {
    $targets += @("$root/artifacts", "$backend/.pytest_cache", "$backend/.mypy_cache", "$backend/.ruff_cache", "$backend/.hypothesis")
}

Write-Step ('Cleaning' + $(if ($all) { ' (all)' } else { '' }))
$removed = 0
foreach ($t in $targets) {
    if (-not (Test-Path $t)) { continue }
    $removed++
    $rel = [IO.Path]::GetRelativePath($root, $t)
    if ($dry) { Write-Info "would delete $rel" } else { Remove-Item -Recurse -Force $t; Write-Info "deleted $rel" }
}
if ($removed -eq 0) { Write-Info 'nothing to delete' }
Write-Ok 'done'
