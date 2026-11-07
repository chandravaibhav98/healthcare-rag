#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# verify-determinism.ps1: SC1 check (N isolated builds, different hash seeds, byte
# comparison). Parity: verify-determinism.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/verify-determinism.ps1 [--runs N] [--corpus DIR] [--save-manifest FILE] [-h|--help]

  --runs N               Number of independent builds to compare (default 2, minimum 2)
  --corpus DIR           Corpus root (default: CORPUS_DIR)
  --save-manifest FILE   Keep the manifest of the first run (for cross-OS comparison)
'@ | Write-Host
}

$cliArgs = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}runs$' { $cliArgs += @('--runs', $args[++$i]) }
        '^-{1,2}corpus$' { $cliArgs += @('--corpus', (Resolve-AbsolutePath $args[++$i])) }
        '^-{1,2}save-manifest$' { $cliArgs += @('--save-manifest', (Resolve-AbsolutePath $args[++$i])) }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
Assert-Command uv 'Run scripts/setup.ps1 first.'

Write-Step 'Determinism check (SC1)'
if (-not (Invoke-Native uv (@('run', '--directory', (Get-BackendDir), 'python', 'scripts/pipeline.py', 'determinism') + $cliArgs))) { exit 1 }
