#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# reproduce.ps1: reproduce every reported metric and the demo from a fresh clone, then
# package the submission bundle. Parity: reproduce.sh, which documents the steps.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/reproduce.ps1 [--quick] [--skip-e2e] [--skip-demo] [--ci] [-h|--help]

  --quick       Metrics only: determinism, evaluation, contract (about 3 minutes)
  --skip-e2e    Skip the Playwright functional suite
  --skip-demo   Skip the demo video (it needs ffmpeg with libx264)
  --ci          Plain output (no colours)

Full run: about 12 minutes. Output: artifacts/submission/.
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('quick', 'skip-e2e', 'skip-demo', 'ci') ${function:Show-Usage}
$e2e = -not ((Test-Flag $args 'quick') -or (Test-Flag $args 'skip-e2e'))
$demo = -not ((Test-Flag $args 'quick') -or (Test-Flag $args 'skip-demo'))
$ciArgs = @()
if (Test-Flag $args 'ci') { $env:NO_COLOR = '1'; $ciArgs = @('--ci') }

Assert-Command uv 'Run scripts/setup.ps1 first.'
Assert-Command git 'Install Git.'
$root = Get-RepoRoot
$backend = Get-BackendDir
$pwsh = (Get-Process -Id $PID).Path
$version = (& git -C $root describe --tags --always --dirty 2>$null)
if (-not $version) { $version = 'unknown' }
$name = "healthcare-rag-submission-$version"
$sub = Join-Path $root 'artifacts/submission'
$out = Join-Path $sub $name
foreach ($p in @($out, (Join-Path $sub "$name.zip"), (Join-Path $sub 'SHA256SUMS'))) {
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
New-Item -ItemType Directory -Force -Path $out | Out-Null
$reports = Join-Path $backend 'evaluation/reports'

function Invoke-Script([string]$Name, [string[]]$ScriptArgs) {
    Invoke-Native $pwsh (@('-NoProfile', '-File', (Join-Path $PSScriptRoot $Name)) + $ScriptArgs)
}

# --- 1. SC1 -------------------------------------------------------------------------------
Write-Step 'SC1: deterministic index (3 isolated builds)'
if (-not (Invoke-Script 'verify-determinism.ps1' @('--runs', '3', '--save-manifest', (Join-Path $out 'determinism-manifest.json')))) {
    Stop-Script 'determinism check failed'
}

# --- 2. SC2 / SC3 -------------------------------------------------------------------------
foreach ($split in @('dev', 'test')) {
    Write-Step "Evaluation: $split"
    if (-not (Invoke-Script 'eval.ps1' @('--split', $split))) { Stop-Script "evaluation ($split) failed" }
    $dir = Get-ChildItem -Path $reports -Directory -Filter "*-eval-$split-*" | Sort-Object Name | Select-Object -Last 1
    if (-not $dir) { Stop-Script "no $split report under $reports" }
    New-Item -ItemType Directory -Force -Path (Join-Path $out 'evaluation') | Out-Null
    Copy-Item -Recurse $dir.FullName (Join-Path $out "evaluation/$split")
}

# --- 3. SC4 -------------------------------------------------------------------------------
Write-Step 'SC4: contract fuzzing (Schemathesis)'
$contract = if (Invoke-Native uv @('run', '--directory', $backend, 'pytest', 'tests/contract', '-q', "--junitxml=$(Join-Path $out 'contract-junit.xml')")) { 'passed' } else { 'failed' }
Write-Info "contract: $contract"

# --- 4. E2E -------------------------------------------------------------------------------
$e2eResult = 'skipped'
if ($e2e) {
    Write-Step 'Functional E2E (Playwright)'
    $e2eDir = Get-E2eDir
    $e2eResult = if (Invoke-Native npm @('--prefix', $e2eDir, 'test')) { 'passed' } else { 'failed' }
    $report = Join-Path $e2eDir 'playwright-report'
    if (Test-Path $report) { Copy-Item -Recurse $report (Join-Path $out 'playwright-report') }
    Write-Info "e2e: $e2eResult"
}

# --- 5. demo ------------------------------------------------------------------------------
$demoResult = 'skipped'
if ($demo) {
    Write-Step 'Demo video'
    $demoResult = if (Invoke-Script 'demo-record.ps1' (@('--gif') + $ciArgs)) { 'passed' } else { 'failed' }
    if ($demoResult -eq 'passed') {
        $demoOut = Join-Path $out 'demo'
        New-Item -ItemType Directory -Force -Path $demoOut | Out-Null
        $mp4 = Get-ChildItem -Path (Join-Path $root 'artifacts/demo') -Filter 'healthcare-rag-demo-*.mp4' | Sort-Object Name | Select-Object -Last 1
        $base = $mp4.FullName.Substring(0, $mp4.FullName.Length - 4)
        Copy-Item $mp4.FullName, "$base.gif", "$base.chapters.txt" $demoOut
    }
}

# --- 6. bundle ----------------------------------------------------------------------------
Write-Step 'Comparing with the recorded results and packaging'
Copy-Item (Join-Path $root 'LICENSE'), (Join-Path $root 'THIRD_PARTY_NOTICES.md') $out
Copy-Item (Join-Path $root 'docs/evaluation-report.md'), (Join-Path $root 'docs/technical-summary.md') $out
(& git -C $root rev-parse HEAD) | Set-Content -NoNewline -Path (Join-Path $out 'COMMIT')
$ok = Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/reproduce_report.py',
    '--out', $out,
    '--dev', (Join-Path $out 'evaluation/dev/summary.json'),
    '--test', (Join-Path $out 'evaluation/test/summary.json'),
    '--determinism', (Join-Path $out 'determinism-manifest.json'),
    '--contract', $contract, '--e2e', $e2eResult, '--demo', $demoResult,
    '--zip', $name)
if (-not $ok) { Stop-Script 'reproduction differs from the record or a gate failed (see above)' }

Write-Step 'Done'
Write-Info "Results:  artifacts/submission/$name/RESULTS.md"
Write-Info "Bundle:   artifacts/submission/$name.zip (checksum in artifacts/submission/SHA256SUMS)"
