#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# docker-up.ps1: build the images and start the Compose stack. Parity: docker-up.sh
# (see it for the start order and what each flag does).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/docker-up.ps1 [--no-build] [--demo] [--observability] [--port N]
                             [--no-smoke] [--ci] [-h|--help]

  --no-build        Use the existing images (rag-api:local, rag-web:local, INDEX_IMAGE)
  --demo            Seed reviewer@/user@ accounts and a week of history. Runs the stack
                    with APP_ENV=staging (demo accounts are refused in production)
  --observability   Also start Prometheus (:9090) and Grafana (:3000)
  --port N          Publish the web app on 127.0.0.1:N (default 8080, saved in .env)
  --no-smoke        Skip the smoke test through nginx
  --ci              Plain output (no colours)
'@ | Write-Host
}

$build = $true; $demo = $false; $obs = $false; $port = ''; $smoke = $true
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}no-build$' { $build = $false }
        '^-{1,2}demo$' { $demo = $true }
        '^-{1,2}observability$' { $obs = $true }
        '^-{1,2}port$' { if ($i + 1 -ge $args.Count) { Stop-Script '--port needs a value' }; $port = $args[++$i] }
        '^-{1,2}no-smoke$' { $smoke = $false }
        '^-{1,2}ci$' { $env:NO_COLOR = '1' }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
if ($port -and $port -notmatch '^\d+$') { Stop-Script '--port must be a number' }

Assert-Docker
$envFile = Get-ComposeEnvPath
Write-Step 'Configuration'
Initialize-ComposeEnv
if ($port) { Set-EnvValue $envFile 'WEB_PORT' $port }
if ($demo) { Set-EnvValue $envFile 'APP_ENV' 'staging' }
$webPort = Get-EnvValue $envFile 'WEB_PORT'; if (-not $webPort) { $webPort = '8080' }
Write-Info "deploy/compose/.env · web port $webPort · APP_ENV $(Get-EnvValue $envFile 'APP_ENV')"

if ($build) {
    $indexVersion = Invoke-ImageBuild 'local'
    Set-EnvValue $envFile 'INDEX_IMAGE' "rag-index:$indexVersion"
    Set-EnvValue $envFile 'API_IMAGE' 'rag-api:local'
    Set-EnvValue $envFile 'WEB_IMAGE' 'rag-web:local'
}

$compose = Get-ComposeArgs -Observability:$obs
Write-Step 'Starting the stack'
if (-not (Invoke-Native docker ($compose + @('up', '-d', '--wait', '--remove-orphans')))) { Stop-Script 'docker compose up failed (scripts/docker-logs.ps1 shows why)' }
Write-Ok 'postgres, api and web are healthy; migrate and indexer finished'

Write-Step 'Seeding accounts'
$seedArgs = $compose + @('run', '--rm', 'seed') + $(if ($demo) { @('--demo') } else { @() })
if (-not (Invoke-Native docker $seedArgs)) { Stop-Script 'seed failed' }

if ($smoke) {
    Write-Step 'Smoke test through nginx'
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'smoke.ps1') --base-url "http://127.0.0.1:$webPort"
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

Write-Step 'Ready'
Write-Info "Web app:  http://localhost:$webPort   (admin@example.org / SEED_ADMIN_PASSWORD in deploy/compose/.env)"
if ($obs) { Write-Info 'Grafana:  http://localhost:3000   (admin / GRAFANA_ADMIN_PASSWORD)  ·  Prometheus: http://localhost:9090' }
Write-Info 'Logs: scripts/docker-logs.ps1 [service] · Stop: scripts/docker-down.ps1'
