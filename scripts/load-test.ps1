#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# load-test.ps1: k6 load test of POST /qa (e2e/load/qa.js). Parity: load-test.sh
# (see it for the gate, the disposable target and the runner selection).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/load-test.ps1 [--vus N] [--duration D] [--target URL] [--port P]
                             [--p95 MS] [--ci] [-h|--help]

  --vus N        Virtual users (default 50)
  --duration D   k6 duration, e.g. 30s, 5m (default 5m)
  --target URL   Use a running API instead of starting a disposable one
  --port P       Port of the disposable API (default 8200)
  --p95 MS       p95 latency threshold in ms (default 300)
  --ci           Plain output (no colours)
'@ | Write-Host
}

$vus = '50'; $duration = '5m'; $target = ''; $port = '8200'; $p95 = '300'
for ($i = 0; $i -lt $args.Count; $i++) {
    $flag = $args[$i]
    $needsValue = $flag -match '^-{1,2}(vus|duration|target|port|p95)$'
    if ($needsValue -and $i + 1 -ge $args.Count) { Stop-Script "$flag needs a value" }
    switch -Regex ($flag) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}vus$' { $vus = $args[++$i] }
        '^-{1,2}duration$' { $duration = $args[++$i] }
        '^-{1,2}target$' { $target = $args[++$i].TrimEnd('/') }
        '^-{1,2}port$' { $port = $args[++$i] }
        '^-{1,2}p95$' { $p95 = $args[++$i] }
        '^-{1,2}ci$' { $env:NO_COLOR = '1' }
        default { [Console]::Error.WriteLine("Unknown option: $flag"); Show-Usage; exit 2 }
    }
}
foreach ($pair in @(@('--vus', $vus), @('--port', $port), @('--p95', $p95))) {
    if ($pair[1] -notmatch '^\d+$') { Stop-Script "$($pair[0]) must be a whole number" }
}

$root = Get-RepoRoot
$backend = Get-BackendDir

# --- runner ----------------------------------------------------------------------------
$runner = $null
if (Get-Command k6 -ErrorAction SilentlyContinue) { $runner = 'local' }
elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) { $runner = 'docker' }
}
if (-not $runner) {
    Stop-Script 'k6 not found and Docker is not running. Install k6 (winget install k6 / brew install k6) or start Docker.'
}

# --- target ----------------------------------------------------------------------------
$server = $null
try {
    if (-not $target) {
        $python = @((Join-Path $backend '.venv/Scripts/python.exe'), (Join-Path $backend '.venv/bin/python')) |
            Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $python) { Stop-Script 'backend/.venv is missing: run scripts/setup.ps1 first.' }
        # Docker Desktop reaches the host through host.docker.internal, which needs the API
        # on all interfaces; elsewhere it stays on loopback.
        $bindHost = if ($runner -eq 'docker' -and -not $IsLinux) { '0.0.0.0' } else { '127.0.0.1' }
        $target = "http://127.0.0.1:$port"
        Write-Step "Starting a disposable API on $target"
        $artifacts = Join-Path $root 'artifacts'
        New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
        # The venv's Python directly (not `uv run`), so stopping $server stops the API itself.
        $server = Start-Process -FilePath $python -WorkingDirectory $backend -PassThru -NoNewWindow `
            -ArgumentList @('scripts/e2e_server.py', '--host', $bindHost, '--port', $port, '--data-dir', 'artifacts/load') `
            -RedirectStandardOutput (Join-Path $artifacts 'load-server.log') `
            -RedirectStandardError (Join-Path $artifacts 'load-server.err.log')
        $ready = $false
        for ($t = 0; $t -lt 120 -and -not $ready; $t++) {
            if ($server.HasExited) { Stop-Script 'the API exited; see artifacts/load-server*.log' }
            try { $ready = (Invoke-WebRequest -Uri "$target/readyz" -TimeoutSec 2 -SkipHttpErrorCheck).StatusCode -eq 200 } catch { $ready = $false }
            if (-not $ready) { Start-Sleep -Seconds 1 }
        }
        if (-not $ready) { Stop-Script 'the API did not become ready; see artifacts/load-server*.log' }
        Write-Ok 'ready (log: artifacts/load-server.log)'
    }

    # --- run ---------------------------------------------------------------------------
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'artifacts/load') | Out-Null
    Write-Step "k6: $vus VUs for $duration against $target ($runner), gate p95 < $p95 ms, 0 % 5xx"
    $k6Env = @('-e', "VUS=$vus", '-e', "DURATION=$duration", '-e', "P95_MS=$p95")
    $script = 'e2e/load/qa.js'
    if ($runner -eq 'local') {
        Push-Location $root
        try { $ok = Invoke-Native k6 (@('run') + $k6Env + @('-e', "BASE_URL=$target", '--summary-export', 'artifacts/load/summary.json', $script)) }
        finally { Pop-Location }
    } else {
        $image = if ($env:K6_IMAGE) { $env:K6_IMAGE } else { 'grafana/k6:latest' }
        if ($IsLinux) { $net = @('--network', 'host'); $dockerTarget = $target }
        else {
            $net = @('--add-host', 'host.docker.internal:host-gateway')
            $dockerTarget = $target -replace '//(127\.0\.0\.1|localhost)', '//host.docker.internal'
        }
        $ok = Invoke-Native docker (@('run', '--rm', '-i') + $net + @('-v', "${root}:/repo", '-w', '/repo', $image, 'run') +
            $k6Env + @('-e', "BASE_URL=$dockerTarget", '--summary-export', 'artifacts/load/summary.json', $script))
    }
    if (-not $ok) { Stop-Script 'load test FAILED (a k6 threshold was crossed; see the summary above)' }
    Write-Ok 'load test passed; summary: artifacts/load/summary.json'
} finally {
    if ($server -and -not $server.HasExited) {
        Write-Info "stopping the disposable API (pid $($server.Id))"
        $server.Kill($true)
    }
}
