#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# k8s-down.ps1: remove the local Kubernetes deployment. Parity: k8s-down.sh.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/k8s-down.ps1 [--namespace-only] [--ci] [-h|--help]

  --namespace-only   Delete only the healthcare-rag namespace (faster re-deploys)
  --ci               Plain output (no colours)
'@ | Write-Host
}

if ((Test-Flag $args 'h') -or (Test-Flag $args 'help')) { Show-Usage; exit 0 }
Assert-KnownFlags $args @('namespace-only', 'ci') ${function:Show-Usage}
$ns = Get-K8sNamespace; $cluster = Get-KindCluster; $context = Get-K8sContext

if (Test-Flag $args 'namespace-only') {
    Assert-Kubectl
    Write-Step "Deleting namespace $ns (database included)"
    if (-not (Invoke-Kube @('delete', 'namespace', $ns, '--ignore-not-found', '--wait=true', '--timeout=180s'))) { Stop-Script 'delete failed' }
    Write-Ok 'namespace removed; cluster kept'
    exit 0
}

if ($context -ne "kind-$cluster") { Stop-Script "refusing to delete a cluster that is not the local kind cluster ($context); use --namespace-only" }
Assert-Command kind 'Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation'
Write-Step "Deleting kind cluster '$cluster'"
if (@(& kind get clusters 2>$null) -contains $cluster) {
    if (-not (Invoke-Native kind @('delete', 'cluster', '--name', $cluster))) { Stop-Script 'kind delete failed' }
    Write-Ok 'cluster deleted'
} else { Write-Info 'no such cluster: nothing to do' }
