#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# docker-logs.ps1: show the Compose stack's logs. Parity: docker-logs.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/docker-logs.ps1 [SERVICE...] [--follow] [--tail N] [-h|--help]

  SERVICE     postgres, migrate, indexer, api, web, prometheus, grafana (default: all)
  --follow    Keep streaming (Ctrl+C to stop)
  --tail N    Lines per service (default 200)
'@ | Write-Host
}

$logArgs = @('--tail', '200'); $services = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^(-f|--follow)$' { $logArgs += '--follow'; break }
        '^-{1,2}tail$' { if ($i + 1 -ge $args.Count) { Stop-Script '--tail needs a value' }; $logArgs += @('--tail', $args[++$i]); break }
        '^-' { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
        default { $services += $args[$i] }
    }
}

Assert-Docker
Set-ComposePlaceholders
& docker ((Get-ComposeArgs -Observability) + @('logs') + $logArgs + $services)
exit $LASTEXITCODE
