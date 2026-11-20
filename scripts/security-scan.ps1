#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# security-scan.ps1: dependency, code and secret scanning. Parity: security-scan.sh
# (see it for what each scanner checks and the failure thresholds).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

# Pinned scanner images (Docker fallback). Trivy: never 0.69.4-0.69.6 (CVE-2026-33634).
$GitleaksImage = if ($env:GITLEAKS_IMAGE) { $env:GITLEAKS_IMAGE } else { 'ghcr.io/gitleaks/gitleaks:v8.30.1' }
$TrivyImage = if ($env:TRIVY_IMAGE) { $env:TRIVY_IMAGE } else { 'aquasec/trivy:0.76.2' }

function Show-Usage {
    @'
Usage: scripts/security-scan.ps1 [--images] [--strict] [--only NAME[,NAME]] [--ci] [-h|--help]

  --images       Also scan the container images (Phase 8+)
  --strict       Fail when gitleaks/trivy are unavailable instead of skipping them
  --only LIST    Run a subset: pip-audit,npm-audit,bandit,gitleaks,trivy
  --ci           Plain output (no colours)
'@ | Write-Host
}

$images = $false; $strict = $false; $only = @()
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}images$' { $images = $true }
        '^-{1,2}strict$' { $strict = $true }
        '^-{1,2}only$' { if ($i + 1 -ge $args.Count) { Stop-Script '--only needs a value' }; $only = $args[++$i] -split ',' }
        '^-{1,2}ci$' { $env:NO_COLOR = '1' }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
function Test-Wanted([string]$Name) { ($only.Count -eq 0) -or ($only -contains $Name) }

$root = Get-RepoRoot
$backend = Get-BackendDir
function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}
function Skip-Scanner([string]$Name) {
    if ($strict) { Add-StepFailure "$Name (unavailable: not installed and Docker is not running)" }
    else { Write-Warn "$Name skipped: install it or start Docker (CI runs it with --strict)" }
}
$dockerBase = @('run', '--rm', '-v', "${root}:/repo", '-w', '/repo')

if (Test-Wanted 'pip-audit') {
    Assert-Command uv 'Run scripts/setup.ps1 first.'
    Write-Step 'pip-audit (backend)'
    Invoke-Step 'pip-audit' uv @('run', '--directory', $backend, 'pip-audit', '--skip-editable', '--progress-spinner', 'off')
}

if (Test-Wanted 'npm-audit') {
    Assert-Command npm 'Run scripts/setup.ps1 first.'
    Write-Step 'npm audit (frontend, e2e)'
    Invoke-Step 'npm audit frontend' npm @('--prefix', (Get-FrontendDir), 'audit', '--audit-level=high')
    Invoke-Step 'npm audit e2e' npm @('--prefix', (Get-E2eDir), 'audit', '--audit-level=high')
}

if (Test-Wanted 'bandit') {
    Write-Step 'bandit (backend code)'
    Invoke-Step 'bandit' uv @('run', '--directory', $backend, 'bandit', '-q', '-r', 'app', 'evaluation', 'scripts', '--severity-level', 'medium')
}

if (Test-Wanted 'gitleaks') {
    Write-Step 'gitleaks (secrets)'
    & git -C $root rev-parse --is-inside-work-tree *> $null
    $glArgs = if ($LASTEXITCODE -eq 0) { @('git', '--redact', '--no-banner', '.') } else { @('dir', '--redact', '--no-banner', '.') }
    if (Get-Command gitleaks -ErrorAction SilentlyContinue) {
        Push-Location $root
        try { Invoke-Step 'gitleaks' gitleaks $glArgs } finally { Pop-Location }
    } elseif (Test-Docker) {
        Invoke-Step 'gitleaks (docker)' docker ($dockerBase + @($GitleaksImage) + $glArgs)
    } else { Skip-Scanner 'gitleaks' }
}

if (Test-Wanted 'trivy') {
    Write-Step 'trivy fs (lockfiles, IaC)'
    $trivyArgs = @('fs', '--scanners', 'vuln,misconfig', '--severity', 'HIGH,CRITICAL', '--exit-code', '1',
        '--skip-dirs', 'node_modules', '--skip-dirs', '.venv', '--skip-dirs', 'artifacts', '--no-progress', '.')
    if (Get-Command trivy -ErrorAction SilentlyContinue) {
        Push-Location $root
        try { Invoke-Step 'trivy fs' trivy $trivyArgs } finally { Pop-Location }
    } elseif (Test-Docker) {
        Invoke-Step 'trivy fs (docker)' docker ($dockerBase + @($TrivyImage) + $trivyArgs)
    } else { Skip-Scanner 'trivy' }
    if ($images) {
        Write-Step 'trivy image'
        Write-Warn 'no container images yet: image scanning arrives with the Dockerfiles (plan Phase 8)'
    }
}

Complete-Steps 'Security scan'
