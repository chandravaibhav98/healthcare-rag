#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# docker-down.ps1: stop the Compose stack (observability profile included).
# Parity: docker-down.sh. Data volumes are kept unless --volumes is given.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/docker-down.ps1 [--volumes] [--ci] [-h|--help]

  --volumes   Also delete the volumes: database, index, Prometheus and Grafana data
  --ci        Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('volumes', 'ci') ${function:Show-Usage}
$volumes = Test-Flag $args 'volumes'

Assert-Docker
Set-ComposePlaceholders
Write-Step 'Stopping the stack'
$downArgs = (Get-ComposeArgs -Observability) + @('--profile', 'tools', 'down', '--remove-orphans') + $(if ($volumes) { @('--volumes') } else { @() })
if (-not (Invoke-Native docker $downArgs)) { Stop-Script 'docker compose down failed' }
if ($volumes) { Write-Ok 'stopped; volumes deleted' } else { Write-Ok 'stopped; volumes kept (--volumes deletes them)' }
