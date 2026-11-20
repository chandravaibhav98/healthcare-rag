#!/usr/bin/env pwsh
# -----------------------------------------------------------------------------
# github-protect.ps1: apply the repository rulesets in .github/rulesets/ with the GitHub
# CLI (default branch: PR + `ci-passed` required; v* tags immutable). Parity:
# github-protect.sh, which documents the rules. Idempotent: rulesets are matched by name.
# -----------------------------------------------------------------------------
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'lib/Common.psm1') -Force

function Show-Usage {
    @'
Usage: scripts/github-protect.ps1 [--repo OWNER/NAME] [--dry-run] [--ci] [-h|--help]

  --repo OWNER/NAME   Target repository (default: the current checkout's GitHub remote)
  --dry-run           Show what would be created or updated; change nothing
  --ci                Plain output (no colours)
'@ | Write-Host
}

$repo = ''; $dry = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    switch -Regex ($args[$i]) {
        '^-{1,2}(h|help)$' { Show-Usage; exit 0 }
        '^-{1,2}repo$' { if ($i + 1 -ge $args.Count) { Stop-Script '--repo needs a value' }; $repo = $args[++$i]; break }
        '^-{1,2}dry-run$' { $dry = $true; break }
        '^-{1,2}ci$' { $env:NO_COLOR = '1'; break }
        default { [Console]::Error.WriteLine("Unknown option: $($args[$i])"); Show-Usage; exit 2 }
    }
}

Assert-Command gh 'Install the GitHub CLI: https://cli.github.com, then run: gh auth login'
if (-not $repo) {
    $repo = (& gh repo view --json nameWithOwner -q .nameWithOwner 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $repo) { Stop-Script 'not a GitHub checkout; pass --repo OWNER/NAME' }
}
$rulesDir = Join-Path (Get-RepoRoot) '.github/rulesets'

Write-Step "Repository $repo"
$info = & gh api "repos/$repo" 2>$null | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $info) { Stop-Script "cannot read $repo (check the name and gh auth status)" }
Write-Info "visibility: $($info.visibility) · admin: $($info.permissions.admin)"
if (-not $info.permissions.admin) { Stop-Script "you need admin rights on $repo to manage rulesets" }

$existing = @(& gh api "repos/$repo/rulesets?includes_parents=false" --paginate 2>$null | ConvertFrom-Json)
$failed = $false
foreach ($file in Get-ChildItem -Path $rulesDir -Filter '*.json' | Sort-Object Name) {
    $name = (Get-Content -Raw $file.FullName | ConvertFrom-Json).name
    $match = @($existing | Where-Object { $_.name -eq $name })
    if ($match.Count -gt 0) { $verb = 'update'; $method = 'PUT'; $path = "repos/$repo/rulesets/$($match[0].id)" }
    else { $verb = 'create'; $method = 'POST'; $path = "repos/$repo/rulesets" }
    if ($dry) { Write-Info "would ${verb}: $name ($($file.Name))"; continue }
    $out = & gh api --method $method $path --input $file.FullName 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) { Write-Ok "${verb}d: $name" }
    else {
        $failed = $true
        Write-Err "could not $verb '$name': $($out.Substring(0, [Math]::Min(300, $out.Length)))"
        if ($out -match '403' -and $info.visibility -eq 'private') {
            Write-Warn 'rulesets on a private repository need GitHub Pro, Team or Enterprise.'
            Write-Warn 'Make the repository public, or upgrade the plan, then re-run (docs/releasing.md).'
        }
    }
}
if ($failed) { exit 1 }

if (-not $dry) {
    Write-Step 'Active rulesets'
    & gh api "repos/$repo/rulesets" --jq '.[] | "    \(.name) [\(.target), \(.enforcement)]"'
    Write-Info 'Required check: ci-passed (GitHub Actions). Test it with a PR that breaks a gate.'
}
