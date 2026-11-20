#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# test.ps1: run the selected test layers. Parity: scripts/test.sh (see it for the
# layer and coverage-gate details).
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
  --e2e        Playwright functional E2E (e2e/tests)
  --all        Backend + frontend + E2E
  --coverage   Coverage reports AND gates (backend ≥80/85/90 %, frontend ≥70 %)
  --ci         Plain output (no colours)

  Default (no layer chosen): backend + frontend.
  E2E environment: CHROME_PATH (use an installed Chrome), E2E_BASE_URL (external stack).
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('backend', 'frontend', 'e2e', 'all', 'coverage', 'ci') ${function:Show-Usage}

$doBackend = (Test-Flag $args 'backend') -or (Test-Flag $args 'all')
$doFrontend = (Test-Flag $args 'frontend') -or (Test-Flag $args 'all')
$doE2e = (Test-Flag $args 'e2e') -or (Test-Flag $args 'all')
if (-not ($doBackend -or $doFrontend -or $doE2e)) { $doBackend = $true; $doFrontend = $true }
$coverage = Test-Flag $args 'coverage'
$backend = Get-BackendDir
$frontend = Get-FrontendDir

if ($doBackend) {
    Assert-Command uv 'Run scripts/setup.ps1 first.'
    Write-Step 'Backend tests'
    if ($coverage) {
        Invoke-Step 'pytest (coverage)' uv @('run', '--directory', $backend, 'pytest', '--cov', '--cov-report=term', '--cov-report=xml', '--cov-report=json')
        Invoke-Step 'coverage gate' uv @('run', '--directory', $backend, 'python', 'scripts/coverage_gate.py', 'coverage.json')
    } else {
        Invoke-Step 'pytest' uv @('run', '--directory', $backend, 'pytest')
    }
}

if ($doFrontend) {
    Assert-Command npm 'Run scripts/setup.ps1 first.'
    Write-Step 'Frontend tests'
    if ($coverage) {
        # Thresholds live in vite.config.ts, so vitest itself fails below 70 %.
        Invoke-Step 'vitest (coverage gate)' npm @('--prefix', $frontend, 'run', '-s', 'test:coverage')
    } else {
        Invoke-Step 'vitest' npm @('--prefix', $frontend, 'run', '-s', 'test')
    }
}

if ($doE2e) {
    Assert-Command npm 'Run scripts/setup.ps1 first.'
    Write-Step 'E2E tests (Playwright)'
    $e2e = Get-E2eDir
    if (-not (Test-Path (Join-Path $e2e 'node_modules'))) {
        Stop-Script 'e2e/node_modules is missing: run scripts/setup.ps1 (or npm ci --prefix e2e).'
    }
    Invoke-Step 'playwright' npm @('--prefix', $e2e, 'run', '-s', 'test')
    Write-Info 'HTML report: npm --prefix e2e run report'
}

Complete-Steps 'Tests'
