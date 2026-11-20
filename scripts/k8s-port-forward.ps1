#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# k8s-port-forward.ps1: reach the app without the gateway's NodePort. Parity:
# k8s-port-forward.sh. Ctrl+C stops it.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/k8s-port-forward.ps1 [--service web|api] [--port N] [-h|--help]

  --service   web (default) or api
  --port N    Local port (default 8089 for web, 8000 for api)
'@ | Write-Host
}

$service = 'web'; $port = ''
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}service$' { if ($i + 1 -ge $args.Count) { Stop-Script '--service needs a value' }; $service = $args[++$i] }
        '^-{1,2}port$' { if ($i + 1 -ge $args.Count) { Stop-Script '--port needs a value' }; $port = $args[++$i] }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
switch ($service) {
    'web' { $target = 8080; if (-not $port) { $port = '8089' } }
    'api' { $target = 8000; if (-not $port) { $port = '8000' } }
    default { Stop-Script '--service must be web or api' }
}
Assert-Kubectl
Write-Step "Forwarding http://127.0.0.1:$port → service/${service}:$target (Ctrl+C to stop)"
while ($true) {
    & kubectl --context (Get-K8sContext) -n (Get-K8sNamespace) port-forward --address 127.0.0.1 "service/$service" "${port}:$target"
    Write-Warn 'port-forward ended (pod replaced?); reconnecting in 2 s'
    Start-Sleep -Seconds 2
}
