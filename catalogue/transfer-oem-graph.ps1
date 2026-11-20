[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateCount(1,100000)][int[]]$ModificationId,
    [string]$Checkpoint = (Join-Path $env:LOCALAPPDATA 'CarPot\OEM-graph'),
    [switch]$ApplyToStaging,
    [ValidateRange(1,65535)][int]$TunnelPort = 3307,
    [string]$TargetServerUuid,
    [ValidateSet('catalogue','railway')][string]$TargetDatabase = 'railway'
)
$ErrorActionPreference = 'Stop'
if ($ModificationId.Where({ $_ -le 0 }).Count) { throw 'Use positive passenger modification IDs.' }
if ($ApplyToStaging -and ($TunnelPort -eq 3306 -or $TargetServerUuid -notmatch '^[a-fA-F0-9-]{36}$')) {
    throw 'Supply a separate Catalogue staging tunnel port and verified MySQL server UUID.'
}
New-Item -ItemType Directory -Force $Checkpoint | Out-Null
$venv = Join-Path $Checkpoint 'python'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $python)) {
    py -3 -m venv $venv
    if ($LASTEXITCODE) { throw 'Python environment setup failed.' }
}
$importer = Join-Path $PSScriptRoot 'vehicle_source_batch.py'
function Invoke-Importer([string[]]$Arguments) {
    & $python $importer @Arguments
    if ($LASTEXITCODE) { throw "Exporter or uploader failed. Resume with the same IDs and checkpoint." }
}
& $python -m pip --disable-pip-version-check install 'PyMySQL==1.1.1'
if ($LASTEXITCODE) { throw 'PyMySQL setup failed.' }
$source = Get-Credential -Message 'Local td1q2018 account with SELECT privileges'
try {
    $env:SOURCE_HOST = '127.0.0.1'
    $env:SOURCE_PORT = '3306'
    $env:SOURCE_DATABASE = 'td1q2018'
    $env:SOURCE_USER = $source.UserName
    $env:SOURCE_PASSWORD = $source.GetNetworkCredential().Password
    if ($ApplyToStaging) {
        $target = Get-Credential -Message 'Catalogue staging MySQL over the existing local tunnel'
        $env:DEST_HOST = '127.0.0.1'
        $env:DEST_PORT = "$TunnelPort"
        $env:DEST_DATABASE = $TargetDatabase
        $env:DEST_USER = $target.UserName
        $env:DEST_PASSWORD = $target.GetNetworkCredential().Password
        Invoke-Importer @('inventory','--confirm-catalogue-staging','--target-server-uuid',$TargetServerUuid,'--output',(Join-Path $Checkpoint 'staging-before'))
    }
    foreach ($id in ($ModificationId | Sort-Object -Unique)) {
        $folder = Join-Path $Checkpoint "passenger-$id"
        Invoke-Importer @('export','--graph-only','--with-oem','--car-id',"$id",'--max-modifications','1','--output',$folder)
        $manifest = Join-Path $folder 'manifest.json'
        $sha = (Get-FileHash -Algorithm SHA256 $manifest).Hash.ToLowerInvariant()
        Invoke-Importer @('validate','--output',$folder,'--manifest-sha256',$sha)
        if ($ApplyToStaging) {
            Invoke-Importer @('upload','--confirm-catalogue-staging','--target-server-uuid',$TargetServerUuid,'--output',$folder,'--manifest-sha256',$sha)
        }
    }
    if ($ApplyToStaging) {
        Invoke-Importer @('inventory','--confirm-catalogue-staging','--target-server-uuid',$TargetServerUuid,'--output',(Join-Path $Checkpoint 'staging-after'))
    }
} finally {
    foreach ($name in @('SOURCE_PASSWORD','SOURCE_USER','SOURCE_HOST','SOURCE_PORT','SOURCE_DATABASE','DEST_PASSWORD','DEST_USER','DEST_HOST','DEST_PORT','DEST_DATABASE')) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
}
