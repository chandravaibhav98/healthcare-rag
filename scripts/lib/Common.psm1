# -----------------------------------------------------------------------------
# scripts/lib/Common.psm1: shared helpers for every PowerShell script in scripts/.
# Bash parity: scripts/lib/common.sh.
#
#   Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force
# -----------------------------------------------------------------------------
Set-StrictMode -Version Latest

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script:StepFailures = [System.Collections.Generic.List[string]]::new()

# UTF-8 mode for every Python process (parity with common.sh).
$env:PYTHONUTF8 = '1'

$useColor = -not ($env:NO_COLOR -or $env:CI -or [Console]::IsOutputRedirected)
$e = [char]27
$script:C = if ($useColor) {
    @{ Blue = "$e[34m"; Green = "$e[32m"; Yellow = "$e[33m"; Red = "$e[31m"; Bold = "$e[1m"; Dim = "$e[2m"; Off = "$e[0m" }
} else {
    @{ Blue = ''; Green = ''; Yellow = ''; Red = ''; Bold = ''; Dim = ''; Off = '' }
}

function Get-RepoRoot { $script:RepoRoot }
function Get-BackendDir { Join-Path $script:RepoRoot 'backend' }
function Get-FrontendDir { Join-Path $script:RepoRoot 'frontend' }

function Write-Step([string]$Message) { Write-Host ''; Write-Host "$($C.Blue)==>$($C.Off) $($C.Bold)$Message$($C.Off)" }
function Write-Info([string]$Message) { Write-Host "    $Message" }
function Write-Ok([string]$Message) { Write-Host "    $($C.Green)✔$($C.Off) $Message" }
function Write-Warn([string]$Message) { Write-Host "    $($C.Yellow)!$($C.Off) $Message" }
function Write-Err([string]$Message) { Write-Host "    $($C.Red)✘$($C.Off) $Message" }

function Stop-Script([string]$Message) {
    Write-Err $Message
    exit 1
}

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Stop-Script "'$Name' is required but not installed. $Hint"
    }
}

# Invoke-Native: echo, run a native command, return $true when its exit code is 0.
function Invoke-Native {
    param([Parameter(Mandatory)][string]$Command, [string[]]$Arguments = @())
    Write-Host "    $($C.Dim)`$ $Command $($Arguments -join ' ')$($C.Off)"
    # Out-Host keeps the tool's output on screen instead of in this function's return value.
    & $Command @Arguments | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# Invoke-Step: run and record failure instead of aborting (parity with run_step).
function Invoke-Step {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @()
    )
    $ok = $false
    try { $ok = Invoke-Native -Command $Command -Arguments $Arguments }
    catch { Write-Err $_.Exception.Message }
    if ($ok) { Write-Ok $Label } else { Write-Err $Label; $script:StepFailures.Add($Label) }
}

function Complete-Steps([string]$Name) {
    if ($script:StepFailures.Count -gt 0) {
        Write-Host ''
        Write-Host "$($C.Red)$Name FAILED$($C.Off) ($($script:StepFailures.Count)): $($script:StepFailures -join ', ')"
        exit 1
    }
    Write-Host ''
    Write-Host "$($C.Green)$Name passed.$($C.Off)"
}

# Resolve-AbsolutePath: absolute path whose target need not exist (parity with abs_path).
function Resolve-AbsolutePath([string]$Path) {
    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $Path))
}

# Import-DotEnv: KEY=VALUE pairs into the process env; existing variables win.
function Import-DotEnv([string]$Path = (Join-Path $script:RepoRoot '.env')) {
    if (-not (Test-Path $Path)) { return }
    foreach ($line in Get-Content -Path $Path -Encoding utf8) {
        if ($line -match '^\s*#' -or $line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $key = $Matches[1]; $value = $Matches[2]
        if (-not (Test-Path "Env:$key")) { Set-Item -Path "Env:$key" -Value $value }
    }
}

# Test-Flag: accept both "--name" (bash style) and "-name" (PowerShell style).
function Test-Flag([string[]]$ArgList, [string]$Name) {
    foreach ($a in $ArgList) { if ($a -match "^-{1,2}$([regex]::Escape($Name))$") { return $true } }
    return $false
}

# Assert-KnownFlags: exit 2 on any argument not in the allowed list.
function Assert-KnownFlags([string[]]$ArgList, [string[]]$Allowed, [scriptblock]$Usage) {
    foreach ($a in $ArgList) {
        $name = $a -replace '^-{1,2}', ''
        if ($Allowed -notcontains $name) {
            [Console]::Error.WriteLine("Unknown option: $a")
            & $Usage
            exit 2
        }
    }
}

Export-ModuleMember -Function * -Variable C
