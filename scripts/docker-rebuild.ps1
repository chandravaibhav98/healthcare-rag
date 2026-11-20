#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# docker-rebuild.ps1: rebuild the images and recreate the containers that changed.
# Parity: docker-rebuild.sh. Data volumes are kept.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/docker-rebuild.ps1 [--no-cache] [--observability] [--ci] [-h|--help]

  --no-cache        Rebuild every layer (e.g. to pick up base-image security fixes)
  --observability   Keep the observability profile running
  --ci              Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('no-cache', 'observability', 'ci') ${function:Show-Usage}
$extra = if (Test-Flag $args 'no-cache') { @('--no-cache', '--pull') } else { @() }

Assert-Docker
Initialize-ComposeEnv
$indexVersion = Invoke-ImageBuild 'local' $extra
Set-EnvValue (Get-ComposeEnvPath) 'INDEX_IMAGE' "rag-index:$indexVersion"
Write-Step 'Recreating changed containers'
$upArgs = (Get-ComposeArgs -Observability:(Test-Flag $args 'observability')) + @('up', '-d', '--wait', '--remove-orphans')
if (-not (Invoke-Native docker $upArgs)) { Stop-Script 'docker compose up failed' }
Write-Ok "stack is healthy (index $indexVersion)"
