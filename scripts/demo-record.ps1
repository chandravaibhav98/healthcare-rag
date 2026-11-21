#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# demo-record.ps1: record the narrated product demo (plan Phase 11) and convert it to
# an MP4 with chapter markers. Parity: demo-record.sh, which documents the steps.
# Output: artifacts/demo/healthcare-rag-demo-<timestamp>.mp4 (+ .chapters.txt).
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/demo-record.ps1 [--target URL --password PW] [--slow-mo MS] [--gif]
                               [--keep-webm] [--crf N] [--ci] [-h|--help]

  --target URL     Record against a running, demo-seeded stack (default: start a fresh one)
  --password PW    Password of admin@example.org on --target (or E2E_PASSWORD)
  --slow-mo MS     Delay per browser action in ms (default 120)
  --gif            Also write a 12-second GIF teaser (960 px wide)
  --keep-webm      Keep Playwright's raw .webm and test output
  --crf N          H.264 quality, lower = better and larger (default 20)
  --ci             Plain output (no colours)

Needs: uv, npm (e2e installed by scripts/setup.ps1), ffmpeg with libx264 on PATH
(winget install Gyan.FFmpeg).
'@ | Write-Host
}

$target = ''; $password = $env:E2E_PASSWORD; $slowMo = '120'; $gif = $false; $keep = $false; $crf = '20'
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}target$' { if ($i + 1 -ge $args.Count) { Stop-Script '--target needs a value' }; $target = "$($args[++$i])".TrimEnd('/'); break }
        '^-{1,2}password$' { if ($i + 1 -ge $args.Count) { Stop-Script '--password needs a value' }; $password = "$($args[++$i])"; break }
        '^-{1,2}slow-mo$' { if ($i + 1 -ge $args.Count) { Stop-Script '--slow-mo needs a value' }; $slowMo = "$($args[++$i])"; break }
        '^-{1,2}gif$' { $gif = $true; break }
        '^-{1,2}keep-webm$' { $keep = $true; break }
        '^-{1,2}crf$' { if ($i + 1 -ge $args.Count) { Stop-Script '--crf needs a value' }; $crf = "$($args[++$i])"; break }
        '^-{1,2}ci$' { $env:NO_COLOR = '1'; break }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}
if ($slowMo -notmatch '^\d+$') { Stop-Script '--slow-mo must be a whole number of milliseconds' }
if ($crf -notmatch '^\d+$' -or [int]$crf -gt 51) { Stop-Script '--crf must be 0-51' }
if ($target -and -not $password) { Stop-Script '--target needs --password (or E2E_PASSWORD)' }

$root = Get-RepoRoot
$e2e = Get-E2eDir
$outDir = Join-Path $root 'artifacts/demo'
$runDir = Join-Path $outDir 'run'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$base = Join-Path $outDir "healthcare-rag-demo-$stamp"

# --- 1. prerequisites -------------------------------------------------------------------
Write-Step 'Prerequisites'
Assert-Command npm 'Install Node (see .nvmrc), then run scripts/setup.ps1'
Assert-Command ffmpeg 'Install ffmpeg: winget install Gyan.FFmpeg (then open a new terminal)'
Assert-Command ffprobe 'ffprobe ships with ffmpeg: winget install Gyan.FFmpeg'
$encoders = (& ffmpeg -hide_banner -encoders 2>$null | Out-String)
if ($encoders -notmatch 'libx264') { Stop-Script 'this ffmpeg has no libx264 (H.264) encoder' }
if (-not (Test-Path (Join-Path $e2e 'node_modules'))) { Stop-Script 'e2e/node_modules is missing: run scripts/setup.ps1 (or npm ci --prefix e2e)' }
if (-not $target) { Assert-Command uv 'Install uv: https://docs.astral.sh/uv/' }
# Playwright records with its own ffmpeg build; with CHROME_PATH it may be missing.
& npm --prefix $e2e exec -- playwright install ffmpeg *> $null
if ($LASTEXITCODE -ne 0) { Write-Warn "could not run 'playwright install ffmpeg' (offline?); recording uses what is installed" }
Write-Ok 'ffmpeg with H.264 and Playwright are available'

if (Test-Path $runDir) { Remove-Item -Recurse -Force $runDir }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# --- 2. the index (cold start) -----------------------------------------------------------
$expectIndex = ''
$indexDir = Join-Path $outDir 'index'
if (-not $target) {
    Write-Step 'Building the index from corpus/ (artifacts/demo/index)'
    if (Test-Path $indexDir) { Remove-Item -Recurse -Force $indexDir }
    $pwsh = (Get-Process -Id $PID).Path
    if (-not (Invoke-Native $pwsh @('-NoProfile', '-File', (Join-Path $PSScriptRoot 'build-index.ps1'), '--out', $indexDir))) { Stop-Script 'index build failed' }
    $expectIndex = (Get-Content -Raw (Join-Path $indexDir 'manifest.json') | ConvertFrom-Json).index_version
    Write-Ok "index_version $expectIndex"
}

# --- 3. record ---------------------------------------------------------------------------
Write-Step 'Recording (about 3.5 minutes; Playwright starts a fresh seeded stack first)'
$saved = @{}
$vars = @('DEMO_SLOW_MO', 'E2E_BASE_URL', 'E2E_PASSWORD', 'E2E_CANDIDATE_INDEX', 'INDEX_DIR', 'DEMO_EXPECT_INDEX')
foreach ($v in $vars) { $saved[$v] = [Environment]::GetEnvironmentVariable($v) }
try {
    $env:DEMO_SLOW_MO = $slowMo
    if ($target) {
        $env:E2E_BASE_URL = $target; $env:E2E_PASSWORD = $password
    } else {
        $env:E2E_CANDIDATE_INDEX = '1'; $env:INDEX_DIR = $indexDir; $env:DEMO_EXPECT_INDEX = $expectIndex
        Remove-Item Env:E2E_BASE_URL, Env:E2E_PASSWORD -ErrorAction SilentlyContinue
    }
    Push-Location $e2e
    try {
        $ok = Invoke-Native npm @('exec', '--', 'playwright', 'test', '--project=demo', '--reporter=list', "--output=$runDir")
    } finally { Pop-Location }
    if (-not $ok) { Stop-Script 'the demo recording failed (see the Playwright output above)' }
} finally {
    foreach ($v in $vars) { [Environment]::SetEnvironmentVariable($v, $saved[$v]) }
}

$webm = Get-ChildItem -Path $runDir -Recurse -Filter '*.webm' -File | Select-Object -First 1
$chapters = Get-ChildItem -Path $runDir -Recurse -Filter 'chapters.json' -File | Select-Object -First 1
if (-not $webm) { Stop-Script "Playwright wrote no video under $runDir" }
if (-not $chapters) { Stop-Script "the demo wrote no chapters.json under $runDir" }
Write-Ok ("raw video: {0:N1} MB" -f ($webm.Length / 1MB))

# --- 4. convert --------------------------------------------------------------------------
Write-Step "Converting to MP4 (H.264, -preset veryfast, CRF $crf, chapters)"
$teaserStart = (& node (Join-Path $e2e 'demo/chapters.mjs') $chapters.FullName $base | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Script 'could not write the chapter files' }
$ffArgs = @('-hide_banner', '-loglevel', 'error', '-y', '-i', $webm.FullName, '-i', "$base.ffmeta",
    '-map', '0:v:0', '-map_metadata', '1', '-map_chapters', '1',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', $crf, '-pix_fmt', 'yuv420p', '-r', '25',
    '-movflags', '+faststart', '-an', "$base.mp4")
if (-not (Invoke-Native ffmpeg $ffArgs)) { Stop-Script 'ffmpeg conversion failed' }
Copy-Item "$base.chapters.txt" (Join-Path $outDir 'demo-chapters.txt') -Force
Remove-Item "$base.ffmeta" -Force

if ($gif) {
    Write-Step 'GIF teaser (12 s from chapter 2)'
    $vf = 'fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer'
    if (-not (Invoke-Native ffmpeg @('-hide_banner', '-loglevel', 'error', '-y', '-ss', $teaserStart, '-t', '12', '-i', "$base.mp4", '-vf', $vf, "$base.gif"))) {
        Stop-Script 'GIF conversion failed'
    }
}

# --- 5. check the result ----------------------------------------------------------------
Write-Step 'Checking the MP4'
function Get-Probe([string[]]$ProbeArgs) { (& ffprobe -v error @ProbeArgs "$base.mp4" | Out-String).Trim() }
$codec = Get-Probe @('-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0')
$size = Get-Probe @('-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0')
$duration = [double](Get-Probe @('-show_entries', 'format=duration', '-of', 'csv=p=0'))
$nchap = @((Get-Probe @('-show_chapters', '-of', 'csv=p=0')) -split "`n" | Where-Object { $_.Trim() }).Count
if ($codec -ne 'h264') { Stop-Script "expected H.264, got $codec" }
if ($size -ne '1920x1080') { Stop-Script "expected 1920x1080, got $size" }
if ($nchap -lt 10) { Stop-Script "expected at least 10 chapters, got $nchap" }
Write-Ok ("h264 $size · {0:N0} s · $nchap chapters · {1:N1} MB" -f $duration, ((Get-Item "$base.mp4").Length / 1MB))

if (-not $keep) { Remove-Item -Recurse -Force $runDir }

$rel = [IO.Path]::GetRelativePath($root, $base)
Write-Step 'Done'
Write-Info "Video:     $rel.mp4"
Write-Info "Chapters:  $rel.chapters.txt (also artifacts/demo/demo-chapters.txt)"
if ($gif) { Write-Info "Teaser:    $rel.gif" }
if ($expectIndex) { Write-Info "Index:     $expectIndex" }
