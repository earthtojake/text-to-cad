#requires -Version 5.1

# This fork is an INDEPENDENT project, not a live mirror of upstream
# (earthtojake/text-to-cad). Upstream has restructured the repo significantly
# (e.g. moved `viewer/` to `skills/render/scripts/viewer/` while this fork
# moved it to `.agents/skills/cad/explorer/`), and merging or rebasing
# upstream into this fork produces tens of rename/rename conflicts plus LFS
# budget rejections from upstream's hosting.
#
# Going forward: do NOT auto-merge upstream. Instead, use this script to PEEK
# at what upstream has, then manually copy/cherry-pick only what you want.
# Usage:
#   .\sync-upstream.ps1            # show summary of new upstream commits
#   .\sync-upstream.ps1 -Files     # also list files changed per commit

param(
    [switch]$Files
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
Set-Location $projectRoot

$upstreamRemote = "upstream"
$upstreamBranch = "main"
$localBranch    = "main"

git remote get-url $upstreamRemote *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Remote '$upstreamRemote' is not configured." -ForegroundColor Red
    exit 1
}

Write-Host "Fetching $upstreamRemote..." -ForegroundColor Cyan
git fetch $upstreamRemote 2>&1 | Where-Object { $_ -notmatch "^Fetching" }

$localSha    = (git rev-parse $localBranch).Trim()
$upstreamSha = (git rev-parse "$upstreamRemote/$upstreamBranch").Trim()

if ($localSha -eq $upstreamSha) {
    Write-Host "main is at the same commit as $upstreamRemote/$upstreamBranch." -ForegroundColor Green
    exit 0
}

$ahead  = [int](git rev-list --count "$upstreamRemote/$upstreamBranch..$localBranch").Trim()
$behind = [int](git rev-list --count "$localBranch..$upstreamRemote/$upstreamBranch").Trim()

Write-Host ""
Write-Host "main is $ahead ahead, $behind behind $upstreamRemote/$upstreamBranch." -ForegroundColor Cyan
Write-Host ""

if ($behind -eq 0) {
    Write-Host "No new upstream commits. Nothing to peek at." -ForegroundColor Green
    exit 0
}

Write-Host "New upstream commits ($behind total):" -ForegroundColor Yellow
git --no-pager log --oneline --reverse "$localBranch..$upstreamRemote/$upstreamBranch"
Write-Host ""

if ($Files) {
    Write-Host "Files changed per upstream commit:" -ForegroundColor Yellow
    git --no-pager log --reverse --stat --format="%n=== %h %s ===" "$localBranch..$upstreamRemote/$upstreamBranch"
    Write-Host ""
}

Write-Host "To bring something in, cherry-pick a single commit:" -ForegroundColor DarkGray
Write-Host "  git cherry-pick <sha>" -ForegroundColor DarkGray
Write-Host "Or copy a single file from upstream without rewriting history:" -ForegroundColor DarkGray
Write-Host "  git checkout $upstreamRemote/$upstreamBranch -- path/to/file" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Do NOT 'git merge $upstreamRemote/$upstreamBranch' or rebase onto it." -ForegroundColor Red
Write-Host "See header comment for why." -ForegroundColor DarkGray
