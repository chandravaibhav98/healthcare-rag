#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# test.ps1: run the selected test layers. Parity: scripts/test.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/test.ps1 [--backend] [--frontend] [--e2e] [--all] [--coverage] [--ci] [-h|--help]

  --backend    Backend tests (pytest)
  --frontend   Frontend tests (vitest)
  --e2e        Playwright E2E (Phase 7+; currently reports "not available")
  --all        Backend + frontend (default when no layer is chosen)
  --coverage   Coverage reports (backend/coverage.xml, frontend/coverage/)
  --ci         Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('backend', 'frontend', 'e2e', 'all', 'coverage', 'ci') ${function:Show-Usage}

$doBackend = (Test-Flag $args 'backend') -or (Test-Flag $args 'all')
$doFrontend = (Test-Flag $args 'frontend') -or (Test-Flag $args 'all')
$doE2e = Test-Flag $args 'e2e'
if (-not ($doBackend -or $doFrontend -or $doE2e)) { $doBackend = $true; $doFrontend = $true }
$coverage = Test-Flag $args 'coverage'
$backend = Get-BackendDir
$frontend = Get-FrontendDir

if ($doBackend) {
    Assert-Command uv 'Run scripts/setup.ps1 first.'
    Write-Step 'Backend tests'
    if ($coverage) {
        Invoke-Step 'pytest (coverage)' uv @('run', '--directory', $backend, 'pytest', '--cov', '--cov-report=term', '--cov-report=xml')
    } else {
        Invoke-Step 'pytest' uv @('run', '--directory', $backend, 'pytest')
    }
}

if ($doFrontend) {
    Assert-Command npm 'Run scripts/setup.ps1 first.'
    Write-Step 'Frontend tests'
    if ($coverage) {
        Invoke-Step 'vitest (coverage)' npm @('--prefix', $frontend, 'run', '-s', 'test:coverage')
    } else {
        Invoke-Step 'vitest' npm @('--prefix', $frontend, 'run', '-s', 'test')
    }
}

if ($doE2e) {
    Write-Step 'E2E tests'
    Write-Err 'Playwright E2E is not available yet (plan Phase 7).'
    exit 1
}

Complete-Steps 'Tests'
