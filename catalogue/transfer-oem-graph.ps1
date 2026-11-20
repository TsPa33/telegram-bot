[CmdletBinding()]
param(
    [ValidateCount(0,100000)][int[]]$ModificationId = @(),
    [string]$Checkpoint = (Join-Path $env:LOCALAPPDATA 'CarPot\OEM-graph-all'),
    [switch]$ApplyToStaging,
    [ValidateRange(1,65535)][int]$TunnelPort = 50212,
    [string]$TargetServerUuid,
    [ValidateSet('catalogue','railway')][string]$TargetDatabase = 'railway',
    [ValidateRange(1,500)][int]$PageSize = 50,
    [ValidateRange(0,2147483647)][int]$ModelId = 0,
    [ValidateRange(0,1000000)][int]$MaxPages = 0,
    [string]$SourceUser = 'root',
    [switch]$PromptSourcePassword
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# No ModificationId => automatically enumerate passenger modifications from the
# *local* td1q2018 source. This script never touches production.
if (@($ModificationId | Where-Object { $_ -le 0 }).Count -gt 0) {
    throw 'Modification IDs must be positive.'
}
if ($ModelId -gt 0 -and $ModificationId.Count -gt 0) {
    throw 'Choose a whole source model (-ModelId) OR explicit modifications (-ModificationId).'
}
# Isolated model checkpoints: a resumed whole-database crawl must never
# skip records because a previous XC60-only run advanced the same cursor.
if ($ModelId -gt 0) {
    $Checkpoint = Join-Path $Checkpoint "model-$ModelId"
}
if ($ApplyToStaging -and ($TunnelPort -eq 3306 -or $TargetServerUuid -notmatch '^[a-fA-F0-9-]{36}$')) {
    throw 'Supply a separate staging MySQL tunnel port and the independently verified server UUID.'
}
if ($ApplyToStaging -and -not (Test-NetConnection -ComputerName 127.0.0.1 -Port $TunnelPort -InformationLevel Quiet)) {
    throw 'Railway staging tunnel is not reachable. Open the tunnel before applying.'
}

New-Item -ItemType Directory -Force -Path $Checkpoint | Out-Null
$venv = Join-Path $Checkpoint 'python'
$python = Join-Path $venv 'Scripts\python.exe'
$importer = Join-Path $PSScriptRoot 'vehicle_source_batch.py'
if (-not (Test-Path $importer)) { throw 'vehicle_source_batch.py is missing in this checkout.' }
if (-not (Test-Path $python)) {
    py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment setup failed.' }
}
& $python -c 'import pymysql'
if ($LASTEXITCODE -ne 0) {
    & $python -m pip --disable-pip-version-check install 'PyMySQL==1.1.1'
    if ($LASTEXITCODE -ne 0) { throw 'PyMySQL installation failed.' }
}

function Invoke-Importer([string[]]$Arguments) {
    & $python $importer @Arguments
    if ($LASTEXITCODE -ne 0) { throw "OEM graph step failed (exit $LASTEXITCODE). Resume using the same checkpoint." }
}

function Get-SecretText([string]$Prompt) {
    $secret = Read-Host $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr); Remove-Variable secret }
}

function Write-Cursor([int]$Value) {
    $destination = Join-Path $Checkpoint ($(if ($ApplyToStaging) { 'passenger-cursor-staging.txt' } else { 'passenger-cursor-export.txt' }))
    $temporary = "$destination.tmp"
    [IO.File]::WriteAllText($temporary, "$Value", [Text.Encoding]::ASCII)
    Move-Item -Force $temporary $destination
}

function Import-One([int]$Id) {
    $folder = Join-Path $Checkpoint "passenger-$Id"
    Invoke-Importer -Arguments @('export','--graph-only','--with-oem','--omit-prd-export',
        '--car-id',"$Id",'--max-modifications','1','--output',$folder)
    $manifest = Join-Path $folder 'manifest.json'
    $sha = (Get-FileHash -Path $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    Invoke-Importer -Arguments @('validate','--output',$folder,'--manifest-sha256',$sha)
    if ($ApplyToStaging) {
        Invoke-Importer -Arguments @('upload','--confirm-catalogue-staging',
            '--target-server-uuid',$TargetServerUuid,'--output',$folder,
            '--manifest-sha256',$sha)
    }
}

$lock = Join-Path $Checkpoint 'transfer.lock'
try {
    $lockStream = [IO.File]::Open($lock,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $lockStream.Dispose()
} catch { throw "Another transfer may be running, or a stale lock exists: $lock" }

try {
    $env:SOURCE_HOST = '127.0.0.1'
    $env:SOURCE_PORT = '3306'
    $env:SOURCE_DATABASE = 'td1q2018'
    $env:SOURCE_USER = $SourceUser
    $env:SOURCE_PASSWORD = ''
    if ($PromptSourcePassword) { $env:SOURCE_PASSWORD = Get-SecretText 'Local MySQL password' }

    if ($ApplyToStaging) {
        $env:DEST_HOST = '127.0.0.1'
        $env:DEST_PORT = "$TunnelPort"
        $env:DEST_DATABASE = $TargetDatabase
        $env:DEST_USER = 'root'
        $env:DEST_PASSWORD = Get-SecretText 'Railway catalogue-staging MySQL password'
        Invoke-Importer -Arguments @('inventory','--confirm-catalogue-staging',
            '--target-server-uuid',$TargetServerUuid,
            '--output',(Join-Path $Checkpoint 'staging-before'))
    }
    if ($ModificationId.Count -gt 0) {
        foreach ($id in ($ModificationId | Sort-Object -Unique)) {
            Write-Host "Processing explicit passenger modification $id" -ForegroundColor Cyan
            Import-One $id
        }
    } else {
        $cursorFile = Join-Path $Checkpoint ($(if ($ApplyToStaging) { 'passenger-cursor-staging.txt' } else { 'passenger-cursor-export.txt' }))
        [int]$after = if (Test-Path $cursorFile) { [int](Get-Content $cursorFile -Raw) } else { 0 }
        $pages = 0
        $total = 0
        $complete = $false
        while (-not $complete) {
            if ($MaxPages -gt 0 -and $pages -ge $MaxPages) { break }
            $discoveryFolder = Join-Path $Checkpoint 'discovery'
            $discoverArgs=@('discover','--after-id',"$after",
                '--scan-limit',"$PageSize",'--output',$discoveryFolder)
            if ($ModelId -gt 0) { $discoverArgs+=@('--model-id',"$ModelId") }
            Invoke-Importer -Arguments $discoverArgs
            $page = Get-Content (Join-Path $discoveryFolder 'discovery.json') -Raw | ConvertFrom-Json
            if ([int]$page.after_id -ne $after -or [int]$page.next_after_id -lt $after -or
                ($ModelId -gt 0 -and [int]$page.model_id -ne $ModelId)) {
                throw 'Discovery checkpoint does not match the requested source model or cursor.'
            }
            foreach ($id in $page.linked_ids) {
                Import-One ([int]$id)
                $total++
            }
            $next = [int]$page.next_after_id
            Write-Cursor $next
            $after = $next
            $pages++
            $complete = [bool]$page.complete
            Write-Host "Pages: $pages; source scanned up to ID: $after; graph imports in this run: $total; done: $complete" -ForegroundColor Cyan
            if (-not $complete -and [int]$page.scanned -eq 0) {
                throw 'Discovery made no progress.'
            }
        }
        if ($complete) {
            Write-Host "PASSENGER GRAPH CRAWL COMPLETE (model ID: $ModelId; model ID 0 means all)" -ForegroundColor Green
        }
        else { Write-Host 'Checkpoint saved. Repeat the same command to continue.' -ForegroundColor Yellow }
    }
    if ($ApplyToStaging) {
        Invoke-Importer -Arguments @('inventory','--confirm-catalogue-staging',
            '--target-server-uuid',$TargetServerUuid,
            '--output',(Join-Path $Checkpoint 'staging-after'))
    }
    Write-Host 'OEM GRAPH TRANSFER FINISHED FOR THE CURRENT RUN' -ForegroundColor Green
}
finally {
    foreach ($name in @('SOURCE_PASSWORD','SOURCE_USER','SOURCE_HOST','SOURCE_PORT','SOURCE_DATABASE',
                       'DEST_PASSWORD','DEST_USER','DEST_HOST','DEST_PORT','DEST_DATABASE')) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
