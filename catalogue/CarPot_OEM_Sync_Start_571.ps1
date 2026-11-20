# CarPot OEM source sync, stage 571. Local MySQL is SELECT-only.
# This launcher does NOT write to Railway and does NOT modify the working checkout.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = 'C:\CarPot\telegram-bot'
$root = 'C:\CarPot\OEM-Audit'
$worktree = Join-Path $root 'oem-sync-571-checkout'
$output = Join-Path $root 'oem-sync-571-data'
$branch = 'feature/carpot-oem-source-model-sync-20261120'

function Assert-Exit([string]$operation) {
    if ($LASTEXITCODE -ne 0) {
        throw "$operation failed (exit code $LASTEXITCODE). Stop; source database remains unchanged."
    }
}

if (-not (Test-Path (Join-Path $repo '.git'))) {
    throw "Repository not found at $repo. Nothing was changed."
}
if (-not (Test-NetConnection 127.0.0.1 -Port 3306 -InformationLevel Quiet)) {
    throw 'Local MySQL port 3306 is not available. Start the local database before running.'
}
New-Item -ItemType Directory -Force -Path $root | Out-Null
Write-Host '1/3 Fetching reviewed CarPot OEM importer...' -ForegroundColor Cyan
& git -C $repo fetch origin $branch
Assert-Exit 'Git fetch'

if (-not (Test-Path $worktree)) {
    & git -C $repo worktree add --detach $worktree "origin/$branch"
    Assert-Exit 'Create isolated Git worktree'
}
if (-not (Test-Path (Join-Path $worktree 'catalogue\transfer-oem-graph.ps1'))) {
    throw "Isolated worktree is incomplete: $worktree"
}
$dirty = & git -C $worktree status --porcelain
Assert-Exit 'Check isolated worktree'
if ($dirty) {
    throw "Isolated worktree contains edits. Preserve them before retrying: $worktree"
}
& git -C $worktree checkout --detach "origin/$branch"
Assert-Exit 'Update isolated worktree'

Write-Host '2/3 Exporting the next source-linked passenger batch across ALL makes...' -ForegroundColor Cyan
Write-Host 'Source: local td1q2018 (read-only). LOCAL spool capped at ~5 GiB; minimum 3 GiB free disk. No Railway writes.'
$script = Join-Path $worktree 'catalogue\transfer-oem-graph.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -PageSize 50 -MaxPages 20 -MaxLocalGiB 5 -MinFreeGiB 3 -Checkpoint $output
Assert-Exit 'MySQL source-only export'

Write-Host '3/3 Finished source-only export.' -ForegroundColor Green
$folder = $output
Write-Host "Source graphs: $folder"
Write-Host 'To inspect/check point:'
Get-ChildItem -Path $folder -Filter 'manifest.json' -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 8 FullName,Length
Write-Host 'Repeat the SAME launcher to resume the next batch; no files are uploaded to Railway yet.' -ForegroundColor Yellow
Write-Host 'No passwords or database credentials need to be shared.' -ForegroundColor Green
