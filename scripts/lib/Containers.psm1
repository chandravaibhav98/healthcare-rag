# -----------------------------------------------------------------------------
# scripts/lib/Containers.psm1: image and Compose helpers shared by docker-*.ps1 and
# k8s-*.ps1 (Phases 8-9). Import after Common.psm1. Bash parity: containers.sh.
# -----------------------------------------------------------------------------
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'Common.psm1')

$script:Root = Get-RepoRoot
$script:ComposeDir = Join-Path $script:Root 'deploy/compose'
$script:ComposeEnv = Join-Path $script:ComposeDir '.env'
$script:DockerDir = Join-Path $script:Root 'deploy/docker'

function Get-ComposeEnvPath { $script:ComposeEnv }

function Assert-Docker {
    Assert-Command docker 'Install Docker Desktop (Windows/macOS) or Docker Engine (Linux).'
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { Stop-Script 'Docker is installed but not running. Start Docker Desktop / the docker service.' }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { Stop-Script "Docker Compose v2 ('docker compose') is required." }
}

# Get-ComposeArgs [-Observability]: arguments for `docker compose` in this repository.
function Get-ComposeArgs([switch]$Observability) {
    $composeArgs = @('compose', '--project-directory', $script:ComposeDir, '-f', (Join-Path $script:ComposeDir 'docker-compose.yml'))
    if ($Observability) { $composeArgs += @('-f', (Join-Path $script:ComposeDir 'docker-compose.observability.yml')) }
    return $composeArgs
}

function New-RandomHex([int]$Bytes) {
    [Convert]::ToHexString([System.Security.Cryptography.RandomNumberGenerator]::GetBytes($Bytes)).ToLowerInvariant()
}

# Initialize-ComposeEnv: create deploy/compose/.env from .env.example, replacing every
# `generate` value with a random secret. Never overwrites an existing file.
function Initialize-ComposeEnv {
    if (Test-Path $script:ComposeEnv) { return }
    $lines = Get-Content (Join-Path $script:ComposeDir '.env.example') | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=generate$') { "$($Matches[1])=$(New-RandomHex 24)" } else { $_ }
    }
    # LF endings and no BOM: Compose reads this file on every OS.
    [System.IO.File]::WriteAllText($script:ComposeEnv, (($lines -join "`n") + "`n"))
    Write-Ok 'created deploy/compose/.env with generated secrets (git-ignored)'
    & docker volume inspect healthcare-rag_pgdata *> $null
    if ($LASTEXITCODE -eq 0) {
        Stop-Script 'a database volume from an earlier deploy/compose/.env exists and keeps its old password. Run scripts/docker-down.ps1 --volumes (deletes the data), then retry.'
    }
}

function Set-ComposePlaceholders {
    if (-not (Test-Path $script:ComposeEnv)) {
        $env:POSTGRES_PASSWORD = 'unused'; $env:JWT_SECRET = 'unused'; $env:GRAFANA_ADMIN_PASSWORD = 'unused' # pragma: allowlist secret (placeholder)
    }
}

function Get-EnvValue([string]$Path, [string]$Key) {
    $line = Get-Content $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -Last 1
    if ($line) { return ($line -split '=', 2)[1] } else { return '' }
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = @(Get-Content $Path)
    $found = $false
    $lines = $lines | ForEach-Object { if ($_ -match "^$Key=") { $found = $true; "$Key=$Value" } else { $_ } }
    if (-not $found) { $lines += "$Key=$Value" }
    [System.IO.File]::WriteAllText($Path, (($lines -join "`n") + "`n"))
}

function Get-ImageIndexVersion([string]$Image) {
    $manifest = (& docker run --rm --network none $Image cat /index/manifest.json) -join "`n"
    if ($LASTEXITCODE -ne 0) { return '' }
    return ($manifest | ConvertFrom-Json).index_version
}

# Invoke-ImageBuild <tag> [extra docker build args]: rag-api:<tag>, rag-web:<tag> and
# rag-index:<index_version>. Returns the index_version. DOCKER_BUILD_ARGS adds flags.
function Invoke-ImageBuild([string]$Tag, [string[]]$Extra = @()) {
    $extraArgs = @($Extra)
    if ($env:DOCKER_BUILD_ARGS) { $extraArgs = @($env:DOCKER_BUILD_ARGS -split '\s+' | Where-Object { $_ }) + $extraArgs }
    Write-Step "Building images (tag $Tag)"
    $builds = @(
        @('index.Dockerfile', 'rag-index:build'),
        @('api.Dockerfile', "rag-api:$Tag"),
        @('web.Dockerfile', "rag-web:$Tag")
    )
    foreach ($b in $builds) {
        $buildArgs = @('build') + $extraArgs + @('-f', (Join-Path $script:DockerDir $b[0]), '-t', $b[1], $script:Root)
        if (-not (Invoke-Native docker $buildArgs)) { Stop-Script "docker build failed: $($b[1])" }
        if ($b[1] -eq 'rag-index:build') {
            $version = Get-ImageIndexVersion 'rag-index:build'
            if (-not $version) { Stop-Script 'could not read index_version from rag-index:build' }
            if (-not (Invoke-Native docker @('tag', 'rag-index:build', "rag-index:$version"))) { Stop-Script 'docker tag failed' }
        }
    }
    Write-Ok "rag-api:$Tag  rag-web:$Tag  rag-index:$version"
    return $version
}

# --- Kubernetes (Phase 9) ---------------------------------------------------------------
$script:KindCluster = 'healthcare-rag'
$script:K8sNamespace = 'healthcare-rag'
$script:K8sDir = Join-Path $script:Root 'deploy/k8s'
$script:EnvoyGatewayVersion = 'v1.10.0'
$script:MetricsServerVersion = 'v0.9.1'

function Get-KindCluster { $script:KindCluster }
function Get-K8sNamespace { $script:K8sNamespace }
function Get-K8sDir { $script:K8sDir }
function Get-EnvoyGatewayVersion { $script:EnvoyGatewayVersion }
function Get-MetricsServerVersion { $script:MetricsServerVersion }
function Get-K8sContext { if ($env:K8S_CONTEXT) { $env:K8S_CONTEXT } else { "kind-$($script:KindCluster)" } }
function Get-K8sBaseUrl { if ($env:K8S_BASE_URL) { $env:K8S_BASE_URL } else { 'http://127.0.0.1:8088' } }

# Invoke-Kube: kubectl against the project context; returns $true on exit code 0.
function Invoke-Kube([string[]]$KubeArgs) {
    return (Invoke-Native kubectl (@('--context', (Get-K8sContext)) + $KubeArgs))
}

function Assert-Kubectl {
    Assert-Command kubectl 'Install kubectl: https://kubernetes.io/docs/tasks/tools/'
    & kubectl --context (Get-K8sContext) version --request-timeout=10s *> $null
    if ($LASTEXITCODE -ne 0) { Stop-Script "kubectl cannot reach context '$(Get-K8sContext)'. Run scripts/k8s-up.ps1 first (or set K8S_CONTEXT)." }
}

function Get-ContentTag([string]$Image) {
    $id = (& docker image inspect --format '{{.Id}}' $Image)
    if ($LASTEXITCODE -ne 0) { Stop-Script "no image $Image" }
    return ($id -replace '^sha256:', '').Substring(0, 12)
}

# Import-ClusterImages: kind load (ctr import fallback), K8S_IMAGE_LOADER, or nothing.
function Import-ClusterImages([string[]]$Images) {
    $context = Get-K8sContext
    if ($context -like 'kind-*') {
        $cluster = $context.Substring(5)
        foreach ($img in $Images) {
            if (-not (Invoke-Native kind @('load', 'docker-image', '--name', $cluster, $img))) {
                Write-Warn "kind load failed for $img; importing with ctr on each node"
                $tar = Join-Path ([System.IO.Path]::GetTempPath()) ("img-" + [guid]::NewGuid() + '.tar')
                try {
                    if (-not (Invoke-Native docker @('save', '-o', $tar, $img))) { Stop-Script "docker save failed: $img" }
                    foreach ($node in (& kind get nodes --name $cluster)) {
                        if (-not (Invoke-Native docker @('cp', $tar, "${node}:/image.tar"))) { Stop-Script "copy to $node failed" }
                        if (-not (Invoke-Native docker @('exec', $node, 'ctr', '-n', 'k8s.io', 'images', 'import', '--all-platforms', '/image.tar'))) { Stop-Script "import into $node failed" }
                        & docker exec $node rm -f /image.tar | Out-Null
                    }
                } finally { Remove-Item -Force $tar -ErrorAction SilentlyContinue }
            }
        }
    } elseif ($env:K8S_IMAGE_LOADER) {
        foreach ($img in $Images) {
            Write-Info "docker save $img | $($env:K8S_IMAGE_LOADER)"
            & bash -c "docker save '$img' | $($env:K8S_IMAGE_LOADER)" | Out-Null
            if ($LASTEXITCODE -ne 0) { Stop-Script "could not load $img" }
        }
    } else {
        Write-Warn "context $context is not kind and K8S_IMAGE_LOADER is unset: the cluster must pull $($Images -join ', ')"
    }
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -SkipHttpErrorCheck -NoProxy
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Get-VenvPython {
    $backend = Get-BackendDir
    $py = @((Join-Path $backend '.venv/Scripts/python.exe'), (Join-Path $backend '.venv/bin/python')) |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $py) { Stop-Script 'backend/.venv is missing: run scripts/setup.ps1 first.' }
    return $py
}

Export-ModuleMember -Function *
