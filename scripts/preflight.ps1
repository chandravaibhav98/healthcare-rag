#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# preflight.ps1 — READ-ONLY environment check run before Phase 0.
#
# Why: finds a missing or outdated toolchain, or repository hygiene that would
# break determinism (CRLF corpus files, risky Windows paths), before any code
# exists. Phase 0's setup.ps1 will call this script first.
#
# It never installs or modifies anything. Exit codes: 0 = ready, 1 = blocking
# problems found, 2 = bad usage. Parity: scripts/preflight.sh (same flags; both
# `--strict` and `-Strict` spellings are accepted).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Show-Usage {
    @'
Usage: scripts/preflight.ps1 [--strict] [--ci] [-h|--help]

Read-only check of the toolchain and repository hygiene needed for Phase 0.

Options:
  --strict   Treat tools needed only by later phases (docker, kubectl, kind,
             k6, ffmpeg) as required instead of optional.
  --ci       Disable colours (also honoured: NO_COLOR=1).
  -h, --help Show this help and exit.

Exit codes: 0 ready · 1 blocking problems found · 2 invalid arguments
'@
}

$Strict = $false
$NoColor = [bool]$env:NO_COLOR
foreach ($a in $args) {
    switch -Regex ($a) {
        '^-{1,2}strict$'        { $Strict = $true; continue }
        '^-{1,2}ci$'            { $NoColor = $true; continue }
        '^(-h|--help|-help)$'   { Show-Usage; exit 0 }
        default { [Console]::Error.WriteLine("Unknown option: $a"); Show-Usage; exit 2 }
    }
}
if ([Console]::IsOutputRedirected) { $NoColor = $true }

$e = [char]27
$C = if ($NoColor) { @{ Ok = ''; Warn = ''; Fail = ''; Dim = ''; Off = '' } }
     else { @{ Ok = "$e[32m"; Warn = "$e[33m"; Fail = "$e[31m"; Dim = "$e[2m"; Off = "$e[0m" } }

$script:Fails = 0
$script:Warns = 0
function Write-Ok([string]$m)   { Write-Host "  $($C.Ok)[ OK ]$($C.Off) $m" }
function Write-Warn([string]$m) { Write-Host "  $($C.Warn)[WARN]$($C.Off) $m"; $script:Warns++ }
function Write-Fail([string]$m) { Write-Host "  $($C.Fail)[FAIL]$($C.Off) $m"; $script:Fails++ }
function Write-Hint([string]$m) { Write-Host "         $($C.Dim)↳ $m$($C.Off)" }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function ConvertTo-Version([string]$text) {
    $m = [regex]::Match($text, '\d+(\.\d+)+')
    if (-not $m.Success) { return $null }
    $parts = @($m.Value.Split('.') | Select-Object -First 4)
    while ($parts.Count -lt 2) { $parts += '0' }
    return [version]($parts -join '.')
}

function Test-Tool {
    param(
        [string]$Label, [string]$Min, [bool]$Required, [string]$Purpose,
        [string]$Install, [string]$Bin, [string[]]$VersionArgs
    )
    $isRequired = $Required -or $Strict
    if (-not (Get-Command $Bin -ErrorAction SilentlyContinue)) {
        if ($isRequired) { Write-Fail "$Label not found (needed: $Purpose)" }
        else { Write-Warn "$Label not found (optional now; needed: $Purpose)" }
        Write-Hint $Install
        return
    }
    $out = try { (& $Bin @VersionArgs 2>&1 | Select-Object -First 3 | Out-String) } catch { '' }
    $ver = ConvertTo-Version $out
    $minVer = ConvertTo-Version $Min
    if ($null -eq $ver) {
        Write-Warn "$Label found but version could not be parsed"
    } elseif ($ver -ge $minVer) {
        Write-Ok "$Label $ver (>= $Min)"
    } elseif ($isRequired) {
        Write-Fail "$Label $ver is older than required $Min ($Purpose)"; Write-Hint $Install
    } else {
        Write-Warn "$Label $ver is older than recommended $Min ($Purpose)"; Write-Hint $Install
    }
}

Write-Host 'Healthcare RAG — pre-flight check'
Write-Host "Repository: $RepoRoot"
Write-Host ''

Write-Host 'Required for Phase 0'
Test-Tool 'git'  '2.30'   $true 'version control'            'winget install Git.Git'                     'git'  @('--version')
Test-Tool 'uv'   '0.5.0'  $true 'Python envs + lockfile'     'winget install astral-sh.uv'                'uv'   @('--version')
Test-Tool 'node' '26.0.0' $true 'frontend tooling (.nvmrc)'  'fnm install  (reads .nvmrc; get fnm: winget install Schniz.fnm)' 'node' @('--version')
Test-Tool 'npm'  '10.0.0' $true 'frontend lockfile'          'Bundled with Node'                          'npm'  @('--version')
# PowerShell itself: this script already runs on 7+, so only check the minimum.
$psv = $PSVersionTable.PSVersion
if ($psv -ge [version]'7.4') { Write-Ok "PowerShell $psv (>= 7.4)" }
else { Write-Warn "PowerShell $psv; 7.4+ recommended"; Write-Hint 'winget install Microsoft.PowerShell' }

if (Get-Command uv -ErrorAction SilentlyContinue) {
    $py = & uv python find 3.12 2>$null
    if ($LASTEXITCODE -eq 0 -and $py) { Write-Ok "Python 3.12 available to uv ($py)" }
    else { Write-Warn 'Python 3.12 not yet installed for uv (uv can fetch it on first use)'; Write-Hint 'uv python install 3.12' }
}

Write-Host ''
Write-Host 'Needed by later phases'
Test-Tool 'docker'  '24.0' $false 'containers (Phase 8)'           'winget install Docker.DockerDesktop'  'docker'  @('--version')
Test-Tool 'kubectl' '1.30' $false 'Kubernetes (Phase 9)'           'winget install Kubernetes.kubectl'    'kubectl' @('version', '--client')
Test-Tool 'kind'    '0.24' $false 'local cluster (Phase 9)'        'winget install Kubernetes.kind'       'kind'    @('version')
Test-Tool 'k6'      '0.50' $false 'load testing (Phase 7)'         'winget install GrafanaLabs.k6'        'k6'      @('version')
Test-Tool 'ffmpeg'  '4.4'  $false 'demo video encoding (Phase 11)' 'winget install Gyan.FFmpeg'           'ffmpeg'  @('-version')

Write-Host ''
Write-Host 'Repository hygiene'
$ga = Join-Path $RepoRoot '.gitattributes'
if ((Test-Path $ga) -and (Select-String -Path $ga -Pattern 'eol=lf' -Quiet)) {
    Write-Ok '.gitattributes enforces LF (determinism, SC1)'
} else {
    Write-Fail '.gitattributes missing or does not enforce eol=lf'
}

if ($RepoRoot -match '[^\x20-\x7E]') {
    Write-Warn 'Repository path contains non-ASCII characters'
    Write-Hint 'Move the repo to a short ASCII path, e.g. C:\dev\healthcare-rag'
} elseif ($RepoRoot.Contains(' ')) {
    Write-Warn 'Repository path contains spaces'
    Write-Hint 'Move the repo to a path without spaces'
} else {
    Write-Ok 'Repository path is ASCII without spaces'
}

if ($IsWindows) {
    if ($RepoRoot.Length -gt 80) {
        Write-Warn "Repository path is $($RepoRoot.Length) chars; node_modules may exceed MAX_PATH (260)"
        Write-Hint 'Use a shorter path, e.g. C:\dev\healthcare-rag'
    }
    $lp = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction SilentlyContinue
    if ($lp -and $lp.LongPathsEnabled -eq 1) { Write-Ok 'Windows long paths enabled' }
    else {
        Write-Warn 'Windows long paths are disabled'
        Write-Hint "Admin PowerShell: Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled 1"
    }
    if ((& git config --global --get core.longpaths 2>$null) -ne 'true') {
        Write-Warn 'git core.longpaths is not enabled'
        Write-Hint 'git config --global core.longpaths true'
    }
}

$inRepo = (& git -C $RepoRoot rev-parse --is-inside-work-tree 2>$null) -eq 'true'
if ($inRepo) {
    $branch = & git -C $RepoRoot symbolic-ref --short HEAD 2>$null
    Write-Ok "Git repository initialised (branch: $(if ($branch) { $branch } else { 'detached' }))"
    if ((& git -C $RepoRoot config --get core.autocrlf 2>$null) -eq 'true') {
        Write-Warn 'core.autocrlf=true (harmless here because .gitattributes overrides it)'
        Write-Hint 'git config core.autocrlf false'
    }
    $crlf = @(& git -C $RepoRoot ls-files --eol 2>$null |
        Where-Object { $_ -match '^i/crlf\s' } |
        ForEach-Object { ($_ -split "`t")[-1] })
    if ($crlf.Count -gt 0) {
        Write-Fail 'Files committed with CRLF line endings:'
        $crlf | ForEach-Object { Write-Host "         $_" }
        Write-Hint "git add --renormalize . ; git commit -m 'chore: normalise line endings'"
    } else {
        Write-Ok 'No CRLF files in the index'
    }
} else {
    Write-Warn 'Not a Git repository yet'
    Write-Hint 'git init -b main   (see docs/project/phase-0-readiness.md)'
}

Write-Host ''
if ($script:Fails -gt 0) {
    Write-Host "$($C.Fail)NOT READY$($C.Off): $($script:Fails) blocking issue(s), $($script:Warns) warning(s)."
    exit 1
}
Write-Host "$($C.Ok)READY for Phase 0$($C.Off) ($($script:Warns) warning(s))."
exit 0
