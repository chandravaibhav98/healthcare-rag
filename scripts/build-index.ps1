#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# build-index.ps1: build the deterministic index, then verify it. Parity: build-index.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/build-index.ps1 [--corpus DIR] [--out DIR] [--inspect] [-h|--help]

  --corpus DIR   Corpus root (default: CORPUS_DIR, i.e. corpus/)
  --out DIR      Output directory (default: INDEX_DIR, i.e. artifacts/index/)
  --inspect      Print chunk statistics after building
'@ | Write-Host
}

$buildArgs = @(); $verifyArgs = @(); $indexArgs = @(); $inspect = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}corpus$' { $p = Resolve-AbsolutePath $args[++$i]; $buildArgs += @('--corpus', $p); $verifyArgs += @('--corpus', $p) }
        '^-{1,2}out$' { $p = Resolve-AbsolutePath $args[++$i]; $buildArgs += @('--out', $p); $indexArgs = @('--index', $p) }
        '^-{1,2}inspect$' { $inspect = $true }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'
$backend = Get-BackendDir

Write-Step 'Build index'
if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', 'scripts/pipeline.py', 'build') + $buildArgs))) { exit 1 }
Write-Step 'Verify index'
if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', 'scripts/pipeline.py', 'verify') + $indexArgs + $verifyArgs))) { exit 1 }
if ($inspect) {
    Write-Step 'Inspect'
    if (-not (Invoke-Native uv (@('run', '--directory', $backend, 'python', 'scripts/pipeline.py', 'inspect', '--stats') + $indexArgs))) { exit 1 }
}
