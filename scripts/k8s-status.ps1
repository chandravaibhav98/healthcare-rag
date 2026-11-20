#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# k8s-status.ps1: what is running, and does it answer. Parity: k8s-status.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/k8s-status.ps1 [--ci] [-h|--help]

Shows nodes, workloads, jobs, autoscaling, disruption budgets, network policies,
the Gateway and the served index_version (K8S_BASE_URL, default http://127.0.0.1:8088).
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('ci') ${function:Show-Usage}
Assert-Kubectl
$ns = Get-K8sNamespace; $ctx = Get-K8sContext; $baseUrl = Get-K8sBaseUrl

Write-Step "Nodes ($ctx)"
& kubectl --context $ctx get nodes -o wide
Write-Step "Workloads in $ns"
& kubectl --context $ctx -n $ns get deployments,statefulsets,pods,jobs -o wide
Write-Step 'Autoscaling, disruption budgets, network policies'
& kubectl --context $ctx -n $ns get hpa,pdb,networkpolicies
Write-Step 'Gateway'
& kubectl --context $ctx -n $ns get gateways,httproutes
Write-Step 'Images'
& kubectl --context $ctx -n $ns get deployment api -o jsonpath='{range .spec.template.spec.initContainers[*]}{"  init "}{.name}{": "}{.image}{"\n"}{end}{range .spec.template.spec.containers[*]}{"  "}{.name}{": "}{.image}{"\n"}{end}'
& kubectl --context $ctx -n $ns get deployment web -o jsonpath='{range .spec.template.spec.containers[*]}{"  "}{.name}{": "}{.image}{"\n"}{end}'
Write-Step "Through the gateway ($baseUrl)"
try {
    $body = (Invoke-WebRequest -Uri "$baseUrl/readyz" -TimeoutSec 5 -NoProxy).Content
    Write-Ok "readyz: $body"
} catch {
    Write-Warn "no answer on $baseUrl (scripts/k8s-port-forward.ps1 is the fallback)"
}
