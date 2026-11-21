#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# lint.ps1: static checks (the same ones CI and pre-commit run). Parity: lint.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/lint.ps1 [--backend] [--frontend] [--fix] [--ci] [-h|--help]

  --backend    Only lint the backend (default: both)
  --frontend   Only lint the frontend (default: both)
  --fix        Apply safe auto-fixes (ruff --fix, ruff format, eslint --fix, prettier --write)
  --ci         Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('backend', 'frontend', 'fix', 'ci') ${function:Show-Usage}

$doBackend = Test-Flag $args 'backend'
$doFrontend = Test-Flag $args 'frontend'
if (-not $doBackend -and -not $doFrontend) { $doBackend = $true; $doFrontend = $true }
$fix = Test-Flag $args 'fix'
$backend = Get-BackendDir
$frontend = Get-FrontendDir

if ($doBackend) {
    Assert-Command uv 'Run scripts/setup.ps1 first.'
    Write-Step 'Backend lint'
    if ($fix) {
        Invoke-Step 'ruff fix' uv @('run', '--directory', $backend, 'ruff', 'check', '--fix', '.')
        Invoke-Step 'ruff format' uv @('run', '--directory', $backend, 'ruff', 'format', '.')
    } else {
        Invoke-Step 'ruff check' uv @('run', '--directory', $backend, 'ruff', 'check', '.')
        Invoke-Step 'ruff format --check' uv @('run', '--directory', $backend, 'ruff', 'format', '--check', '.')
    }
    Invoke-Step 'mypy --strict' uv @('run', '--directory', $backend, 'mypy')
    Invoke-Step 'contract snapshots current' uv @('run', '--directory', $backend, 'python', 'scripts/export_schemas.py', '--check')
}

if ($doFrontend) {
    Assert-Command npm 'Run scripts/setup.ps1 first.'
    Write-Step 'Frontend lint'
    if ($fix) {
        Invoke-Step 'eslint --fix' npm @('--prefix', $frontend, 'run', '-s', 'lint:fix')
        Invoke-Step 'prettier --write' npm @('--prefix', $frontend, 'run', '-s', 'format')
    } else {
        Invoke-Step 'eslint' npm @('--prefix', $frontend, 'run', '-s', 'lint')
        Invoke-Step 'prettier --check' npm @('--prefix', $frontend, 'run', '-s', 'format:check')
    }
    Invoke-Step 'tsc --noEmit' npm @('--prefix', $frontend, 'run', '-s', 'typecheck')
    Invoke-Step 'API types current' npm @('--prefix', $frontend, 'run', '-s', 'gen:api:check')
    # The Playwright suites and the demo (e2e/) are TypeScript too.
    $e2e = Get-E2eDir
    if (Test-Path (Join-Path $e2e 'node_modules')) {
        Invoke-Step 'tsc (e2e, demo)' npm @('--prefix', $e2e, 'run', '-s', 'typecheck')
    }
}

Complete-Steps 'Lint'
