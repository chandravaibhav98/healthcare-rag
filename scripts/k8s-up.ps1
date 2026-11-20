#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# k8s-up.ps1: the full stack on a local kind cluster. Parity: k8s-up.sh (see it for
# the six steps and the environment variables).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/k8s-up.ps1 [--overlay local|prod] [--recreate] [--no-build]
                          [--existing-cluster] [--no-smoke] [--ci] [-h|--help]

  --overlay local     kind cluster + Envoy Gateway + in-cluster PostgreSQL (default)
  --overlay prod      Render deploy/k8s/overlays/prod to artifacts/k8s-prod.yaml only;
                      production is applied by the release pipeline (Phase 10)
  --recreate          Delete and recreate the kind cluster first
  --no-build          Use the existing local images
  --existing-cluster  Use the current K8S_CONTEXT as is: no kind, no platform install
  --no-smoke          Skip the smoke test through the gateway
  --ci                Plain output (no colours)

Environment: K8S_CONTEXT (default kind-healthcare-rag), K8S_BASE_URL (default
http://127.0.0.1:8088), K8S_IMAGE_LOADER (non-kind clusters), DOCKER_BUILD_ARGS.
'@ | Write-Host
}

$overlay = 'local'; $recreate = $false; $build = $true; $existing = $false; $smoke = $true
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}overlay$' { if ($i + 1 -ge $args.Count) { Stop-Script '--overlay needs a value' }; $overlay = $args[++$i] }
        '^-{1,2}recreate$' { $recreate = $true }
        '^-{1,2}no-build$' { $build = $false }
        '^-{1,2}existing-cluster$' { $existing = $true }
        '^-{1,2}no-smoke$' { $smoke = $false }
        '^-{1,2}ci$' { $env:NO_COLOR = '1' }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
$root = Get-RepoRoot
$k8s = Get-K8sDir
$ns = Get-K8sNamespace
$cluster = Get-KindCluster
$context = Get-K8sContext
$baseUrl = Get-K8sBaseUrl
$overlayDir = if ($env:K8S_OVERLAY_DIR) { $env:K8S_OVERLAY_DIR } else { Join-Path $k8s 'overlays/local' }

if ($overlay -eq 'prod') {
    Assert-Command kubectl 'Install kubectl: https://kubernetes.io/docs/tasks/tools/'
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'artifacts') | Out-Null
    if (-not (Invoke-Native kubectl @('kustomize', (Join-Path $k8s 'overlays/prod'), '-o', (Join-Path $root 'artifacts/k8s-prod.yaml')))) { Stop-Script 'kustomize failed' }
    Write-Ok 'rendered artifacts/k8s-prod.yaml'
    Write-Info 'Production is applied by the release pipeline (plan Phase 10), not from a laptop.'
    exit 0
}
if ($overlay -ne 'local') { Stop-Script '--overlay must be local or prod' }

Assert-Docker
Assert-Command kubectl 'Install kubectl: https://kubernetes.io/docs/tasks/tools/'

# --- 1. cluster -------------------------------------------------------------------------
if ($existing) {
    Write-Step "Cluster: existing context $context"
    Assert-Kubectl
} else {
    Assert-Command kind 'Install kind: https://kind.sigs.k8s.io/docs/user/quick-start/#installation'
    if ($context -ne "kind-$cluster") { Stop-Script "with kind, K8S_CONTEXT must be kind-$cluster (or use --existing-cluster)" }
    Write-Step "Cluster: kind '$cluster'"
    $clusters = @(& kind get clusters 2>$null)
    if ($recreate -and ($clusters -contains $cluster)) {
        if (-not (Invoke-Native kind @('delete', 'cluster', '--name', $cluster))) { Stop-Script 'kind delete failed' }
        $clusters = @()
    }
    if ($clusters -contains $cluster) { Write-Ok 'cluster exists' }
    elseif (-not (Invoke-Native kind @('create', 'cluster', '--config', (Join-Path $k8s 'kind/cluster.yaml'), '--wait', '180s'))) { Stop-Script 'kind create failed' }

    # --- 2. platform --------------------------------------------------------------------
    $eg = Get-EnvoyGatewayVersion; $ms = Get-MetricsServerVersion
    Write-Step "Platform: Envoy Gateway $eg, metrics-server $ms"
    & kubectl --context $context -n envoy-gateway-system get deployment envoy-gateway *> $null
    if ($LASTEXITCODE -ne 0) {
        if (-not (Invoke-Kube @('apply', '--server-side', '--force-conflicts', '-f', "https://github.com/envoyproxy/gateway/releases/download/$eg/install.yaml"))) { Stop-Script 'Envoy Gateway install failed' }
    }
    if (-not (Invoke-Kube @('-n', 'envoy-gateway-system', 'wait', 'deployment/envoy-gateway', '--for=condition=Available', '--timeout=300s'))) { Stop-Script 'Envoy Gateway is not available' }
    if (-not (Invoke-Kube @('label', 'namespace', 'envoy-gateway-system', 'healthcare-rag/gateway=true', '--overwrite'))) { Stop-Script 'labelling failed' }
    & kubectl --context $context -n kube-system get deployment metrics-server *> $null
    if ($LASTEXITCODE -ne 0) {
        if (-not (Invoke-Kube @('apply', '-f', "https://github.com/kubernetes-sigs/metrics-server/releases/download/$ms/components.yaml"))) { Stop-Script 'metrics-server install failed' }
        $patch = '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
        if (-not (Invoke-Kube @('-n', 'kube-system', 'patch', 'deployment', 'metrics-server', '--type=json', '-p', $patch))) { Stop-Script 'metrics-server patch failed' }
    }
    Write-Ok 'platform ready'
}

# --- 3. images --------------------------------------------------------------------------
if ($build) { $indexVersion = Invoke-ImageBuild 'local' }
else {
    $indexVersion = Get-ImageIndexVersion 'rag-index:build'
    if (-not $indexVersion) { Stop-Script 'no rag-index:build image; run without --no-build' }
}
$apiTag = Get-ContentTag 'rag-api:local'; $webTag = Get-ContentTag 'rag-web:local'
& docker tag rag-api:local "rag-api:$apiTag"; & docker tag rag-web:local "rag-web:$webTag"
Write-Step 'Loading images into the cluster'
Import-ClusterImages @("rag-api:$apiTag", "rag-web:$webTag", "rag-index:$indexVersion", 'postgres:18-alpine')

# --- 4. secrets -------------------------------------------------------------------------
$secrets = Join-Path $k8s 'overlays/local/secrets.env'
if (-not (Test-Path $secrets)) {
    $pg = New-RandomHex 24
    $content = @(
        "POSTGRES_PASSWORD=$pg",
        "JWT_SECRET=$(New-RandomHex 32)",
        "SEED_ADMIN_PASSWORD=$(New-RandomHex 12)",
        "DATABASE_URL=postgresql+asyncpg://rag:$pg@postgres:5432/rag"
    ) -join "`n"
    [System.IO.File]::WriteAllText($secrets, $content + "`n")
    Write-Ok 'created deploy/k8s/overlays/local/secrets.env (git-ignored)'
}

# --- 5. apply ---------------------------------------------------------------------------
$gen = Join-Path $root 'artifacts/k8s-local'
New-Item -ItemType Directory -Force -Path $gen | Out-Null
$rel = [System.IO.Path]::GetRelativePath($gen, $overlayDir) -replace '\\', '/'
$kustomization = @"
# Generated by scripts/k8s-up.ps1: the local overlay with this build's image tags.
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [$rel]
images:
  - { name: rag-api, newTag: "$apiTag" }
  - { name: rag-web, newTag: "$webTag" }
  - { name: rag-index, newTag: "$indexVersion" }
"@
[System.IO.File]::WriteAllText((Join-Path $gen 'kustomization.yaml'), ($kustomization -replace "`r`n", "`n") + "`n")
Write-Step "Applying the local overlay (index $indexVersion)"
if (-not (Invoke-Kube @('-n', $ns, 'delete', 'job', 'db-migrate', 'db-seed', '--ignore-not-found'))) { Stop-Script 'job cleanup failed' }
if (-not (Invoke-Kube @('apply', '-k', $gen))) { Stop-Script 'kubectl apply failed' }

Write-Step 'Waiting for the rollout'
$waits = @(
    @('-n', $ns, 'rollout', 'status', 'statefulset/postgres', '--timeout=300s'),
    @('-n', $ns, 'wait', 'job/db-migrate', '--for=condition=Complete', '--timeout=600s'),
    @('-n', $ns, 'rollout', 'status', 'deployment/api', '--timeout=300s'),
    @('-n', $ns, 'rollout', 'status', 'deployment/web', '--timeout=300s'),
    @('-n', $ns, 'wait', 'job/db-seed', '--for=condition=Complete', '--timeout=600s'),
    @('-n', $ns, 'wait', 'gateway/hcrag', '--for=condition=Programmed', '--timeout=300s')
)
foreach ($w in $waits) { if (-not (Invoke-Kube $w)) { Stop-Script "timed out: kubectl $($w -join ' ')" } }
Write-Ok 'api, web and postgres ready; migrations and seed done'

# --- 6. smoke ---------------------------------------------------------------------------
if ($smoke) {
    Write-Step "Smoke test through the gateway ($baseUrl)"
    if (-not (Wait-Http "$baseUrl/readyz" 120)) { Stop-Script "the gateway does not answer on $baseUrl (try scripts/k8s-port-forward.ps1)" }
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'smoke.ps1') --base-url $baseUrl
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

Write-Step 'Ready'
Write-Info "Web app: $baseUrl   (admin@example.org / SEED_ADMIN_PASSWORD in deploy/k8s/overlays/local/secrets.env)"
Write-Info 'Status: scripts/k8s-status.ps1 · Checks: scripts/k8s-verify.ps1 · Remove: scripts/k8s-down.ps1'
