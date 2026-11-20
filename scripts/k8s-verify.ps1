#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# k8s-verify.ps1: zero-downtime checks on the running cluster. Parity: k8s-verify.sh
# (see it for what each check proves).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'lib/Containers.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/k8s-verify.ps1 [--vus N] [--duration D] [--skip-restart] [--skip-index]
                              [--ci] [-h|--help]

  --vus N          Virtual users during each check (default 20)
  --duration D     k6 duration per check, long enough to cover the rollout (default 90s)
  --skip-restart   Skip the rolling-restart check
  --skip-index     Skip the index rollout/rollback check
  --ci             Plain output (no colours)
'@ | Write-Host
}

$vus = '20'; $duration = '90s'; $doRestart = $true; $doIndex = $true
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}vus$' { if ($i + 1 -ge $args.Count) { Stop-Script '--vus needs a value' }; $vus = $args[++$i] }
        '^-{1,2}duration$' { if ($i + 1 -ge $args.Count) { Stop-Script '--duration needs a value' }; $duration = $args[++$i] }
        '^-{1,2}skip-restart$' { $doRestart = $false }
        '^-{1,2}skip-index$' { $doIndex = $false }
        '^-{1,2}ci$' { $env:NO_COLOR = '1' }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
$root = Get-RepoRoot; $ns = Get-K8sNamespace; $baseUrl = Get-K8sBaseUrl
Assert-Kubectl
$py = Get-VenvPython
$outDir = Join-Path $root 'artifacts/k8s-verify'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (-not (Wait-Http "$baseUrl/readyz" 30)) { Stop-Script "$baseUrl does not answer; run scripts/k8s-up.ps1 first" }

function Get-ServedVersion {
    try { return (Invoke-RestMethod -Uri "$baseUrl/readyz" -TimeoutSec 5 -NoProxy).index_version } catch { return '' }
}

# 20 consecutive requests must report $Want (terminating pods may answer for a few seconds).
function Assert-ServedVersion([string]$Want) {
    $streak = 0; $deadline = (Get-Date).AddSeconds(60); $got = ''
    while ($streak -lt 20) {
        $got = Get-ServedVersion
        if ($got -eq $Want) { $streak++ } else { $streak = 0; Start-Sleep -Seconds 1 }
        if ((Get-Date) -gt $deadline) { throw "still serving $got 60 s after the rollout, expected $Want" }
    }
    Write-Ok "20 consecutive requests served index $Want"
}

function Start-Load([string]$Name) {
    $log = Join-Path $outDir "$Name.log"
    $job = Start-ThreadJob -ScriptBlock {
        param($script, $target, $vus, $duration, $log)
        & pwsh -NoProfile -File $script --target $target --vus $vus --duration $duration --p95 2000 --ci *> $log
        return $LASTEXITCODE
    } -ArgumentList (Join-Path $PSScriptRoot 'load-test.ps1'), $baseUrl, $vus, $duration, $log
    Start-Sleep -Seconds 8
    return $job
}

function Complete-Load($Job, [string]$Name) {
    $rc = Receive-Job -Job $Job -Wait -AutoRemoveJob
    $summary = Join-Path $outDir "$Name.summary.json"
    Copy-Item (Join-Path $root 'artifacts/load/summary.json') $summary -Force
    $check = @'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))["metrics"]
failed, total = m["http_req_failed"]["passes"], m["http_reqs"]["count"]
bad = m["checks"]["fails"]
print(f"    {sys.argv[2]}: {total} requests, {failed} failed, {bad} failed checks, p95 {m['http_req_duration']['p(95)']:.0f} ms")
sys.exit(1 if failed or bad or total == 0 else 0)
'@
    & $py -c $check $summary $Name
    if ($LASTEXITCODE -ne 0 -or $rc -ne 0) { throw "${Name}: requests failed (log: artifacts/k8s-verify/$Name.log)" }
    Write-Ok "${Name}: zero failed requests"
}

$rolledOut = $false; $loadJob = $null
try {
    if ($doRestart) {
        Write-Step "Rolling restart of api and web under load ($vus VUs)"
        $loadJob = Start-Load 'rolling-restart'
        if (-not (Invoke-Kube @('-n', $ns, 'rollout', 'restart', 'deployment/api', 'deployment/web'))) { throw 'rollout restart failed' }
        foreach ($d in 'api', 'web') { if (-not (Invoke-Kube @('-n', $ns, 'rollout', 'status', "deployment/$d", '--timeout=300s'))) { throw "$d rollout failed" } }
        Complete-Load $loadJob 'rolling-restart'; $loadJob = $null
    }

    if ($doIndex) {
        Assert-Docker
        Write-Step 'Index rollout and rollback under load'
        $current = Get-ServedVersion
        if (-not $current) { throw 'could not read the served index_version' }
        Write-Info "serving $current"
        $extra = @(); if ($env:DOCKER_BUILD_ARGS) { $extra = @($env:DOCKER_BUILD_ARGS -split '\s+' | Where-Object { $_ }) }
        $buildArgs = @('build') + $extra + @('-q', '-f', (Join-Path $root 'deploy/docker/index.Dockerfile'),
            '--build-arg', 'CHUNK_MIN_TOKENS=100', '--build-arg', 'CHUNK_MAX_TOKENS=200', '-t', 'rag-index:candidate', $root)
        if (-not (Invoke-Native docker $buildArgs)) { throw 'candidate index build failed' }
        $candidate = Get-ImageIndexVersion 'rag-index:candidate'
        if (-not $candidate -or $candidate -eq $current) { throw 'the candidate index has no new index_version' }
        & docker tag rag-index:candidate "rag-index:$candidate"
        Import-ClusterImages @("rag-index:$candidate")

        $loadJob = Start-Load 'index-rollout'
        $rolledOut = $true
        if (-not (Invoke-Kube @('-n', $ns, 'set', 'image', 'deployment/api', "index=rag-index:$candidate"))) { throw 'set image failed' }
        Invoke-Kube @('-n', $ns, 'annotate', 'deployment/api', "kubernetes.io/change-cause=index $candidate (k8s-verify)", '--overwrite') | Out-Null
        if (-not (Invoke-Kube @('-n', $ns, 'rollout', 'status', 'deployment/api', '--timeout=300s'))) { throw 'rollout failed' }
        Assert-ServedVersion $candidate
        if (-not (Invoke-Kube @('-n', $ns, 'rollout', 'undo', 'deployment/api'))) { throw 'rollout undo failed' }
        $rolledOut = $false
        if (-not (Invoke-Kube @('-n', $ns, 'rollout', 'status', 'deployment/api', '--timeout=300s'))) { throw 'rollback failed' }
        Assert-ServedVersion $current
        Complete-Load $loadJob 'index-rollout'; $loadJob = $null
        Invoke-Kube @('-n', $ns, 'rollout', 'history', 'deployment/api') | Out-Null
    }
} catch {
    Write-Err $_.Exception.Message
    if ($loadJob) { Stop-Job $loadJob -ErrorAction SilentlyContinue; Remove-Job $loadJob -Force -ErrorAction SilentlyContinue }
    if ($rolledOut) {
        Write-Warn 'restoring the previous index (kubectl rollout undo)'
        & kubectl --context (Get-K8sContext) -n $ns rollout undo deployment/api *> $null
    }
    exit 1
}

Write-Step 'All checks passed'
Write-Info 'k6 summaries: artifacts/k8s-verify/'
