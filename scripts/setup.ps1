#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# setup.ps1: take a clean machine to "lint and tests green" (Phase 0 exit criterion).
# Same steps and flags as scripts/setup.sh; see that file for the step list.
# Both `--flag` and `-flag` spellings are accepted.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/setup.ps1 [--ci] [--skip-playwright] [--skip-hooks] [--no-verify] [-h|--help]

  --ci               Non-interactive CI mode: plain output, no .env, no git hooks
  --skip-playwright  Do not install Playwright browsers (and skip the E2E suite in verify)
  --skip-hooks       Do not install the pre-commit git hooks
  --no-verify        Skip the final lint + test run
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('ci', 'skip-playwright', 'skip-hooks', 'no-verify') ${function:Show-Usage}

$CiMode = Test-Flag $args 'ci'
$SkipPlaywright = Test-Flag $args 'skip-playwright'
$SkipHooks = $CiMode -or (Test-Flag $args 'skip-hooks')
$Verify = -not (Test-Flag $args 'no-verify')
$CiFlag = @(if ($CiMode) { '--ci' })
if ($CiMode) { $env:NO_COLOR = '1' }

$root = Get-RepoRoot
$backend = Get-BackendDir
$frontend = Get-FrontendDir

Write-Step '1/7 Pre-flight checks'
& pwsh -NoProfile -File (Join-Path $root 'scripts/preflight.ps1') @CiFlag
if ($LASTEXITCODE -ne 0) { Stop-Script 'Pre-flight failed: fix the [FAIL] items above, then re-run.' }

Write-Step '2/7 Environment file'
$envFile = Join-Path $root '.env'
if ($CiMode) {
    Write-Info 'CI mode: using code defaults and CI-provided variables (no .env).'
} elseif (Test-Path $envFile) {
    Write-Ok '.env already exists (left untouched)'
} else {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Write-Ok 'created .env from .env.example'
}

Write-Step '3/7 Backend dependencies (uv)'
if (-not (Invoke-Native uv @('sync', '--locked', '--directory', $backend))) { Stop-Script 'uv sync failed' }
Write-Ok 'backend/.venv matches backend/uv.lock'

Write-Step '4/7 Frontend dependencies (npm)'
if (-not (Invoke-Native npm @('ci', '--prefix', $frontend, '--no-audit', '--no-fund'))) { Stop-Script 'npm ci failed' }
Write-Ok 'frontend/node_modules matches frontend/package-lock.json'

Write-Step '5/7 Git hooks (pre-commit)'
if ($SkipHooks) {
    Write-Info 'skipped'
} elseif ((& git -C $root rev-parse --is-inside-work-tree 2>$null) -eq 'true') {
    if (-not (Invoke-Native uv @('run', '--directory', $backend, 'pre-commit', 'install'))) { Stop-Script 'pre-commit install failed' }
    Write-Ok 'pre-commit hooks installed'
} else {
    Write-Warn 'not a Git repository; skipping hook installation'
}

Write-Step '6/7 e2e dependencies + Playwright browsers'
# e2e/ dependencies are always installed: lint type-checks the suites and the demo.
$e2e = Get-E2eDir
if (-not (Invoke-Native npm @('ci', '--prefix', $e2e, '--no-audit', '--no-fund'))) { Stop-Script 'npm ci (e2e) failed' }
if ($SkipPlaywright) {
    Write-Info 'browsers skipped (--skip-playwright); the E2E suite is left out of the verify step'
} else {
    # --with-deps installs OS libraries (sudo on Linux), so only CI asks for it.
    $pwArgs = @('--prefix', $e2e, 'exec', '--', 'playwright', 'install') + $(if ($CiMode) { @('--with-deps', 'chromium') } else { @('chromium') })
    if (-not (Invoke-Native npm $pwArgs)) { Stop-Script 'playwright install failed' }
    Write-Ok 'e2e/node_modules + Playwright Chromium installed'
}

if ($Verify) {
    Write-Step '7/7 Verify: lint + tests'
    & pwsh -NoProfile -File (Join-Path $root 'scripts/lint.ps1') @CiFlag
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    # Without browsers (--skip-playwright) the E2E suite cannot run: CI runs it in its own job.
    $testScope = if ($SkipPlaywright) { @('--backend', '--frontend') } else { @('--all') }
    & pwsh -NoProfile -File (Join-Path $root 'scripts/test.ps1') @testScope @CiFlag
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Step '7/7 Verify: skipped (--no-verify)'
}

Write-Host ''
Write-Host "$($C.Green)Setup complete.$($C.Off) Next: scripts/lint.ps1 · scripts/test.ps1 · see README.md"
