#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# eval.ps1: Phase 4 evaluation (gold check, index if needed, scorecard). Parity: eval.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/eval.ps1 [--split dev|test] [--gate] [--update-baseline] [-h|--help]

  --split dev|test     Gold split (default dev). Run test ONCE per frozen configuration.
  --gate               Fail if dev metrics regress vs backend/evaluation/baseline.json
  --update-baseline    Record the current dev scorecard as the new baseline
  --require-targets    With --gate, also require SC2 (P@5 >= 0.65) and SC3 (>= 0.80)
'@ | Write-Host
}

$split = 'dev'; $extra = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}split$' { $split = $args[++$i] }
        '^-{1,2}(gate|update-baseline|require-targets)$' { $extra += @('--' + ($args[$i] -replace '^-{1,2}', '')) }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
Import-DotEnv
$backend = Get-BackendDir
$index = if ($env:INDEX_DIR) { $env:INDEX_DIR } else { 'artifacts/index' }
if (-not [System.IO.Path]::IsPathRooted($index)) { $index = Join-Path (Get-RepoRoot) $index }

if (-not (Test-Path (Join-Path $index 'manifest.json'))) {
    Write-Step "Build index (none at $index)"
    if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', 'scripts/pipeline.py', 'build'))) { exit 1 }
}
Write-Step 'Gold files are current'
if (-not (Invoke-Native uv @('run', '--directory', $backend, 'python', '-m', 'evaluation.build_gold', '--check'))) { exit 1 }
Write-Step "Evaluate ($split)"
if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', '-m', 'evaluation.run', '--split', $split) + $extra))) { exit 1 }
