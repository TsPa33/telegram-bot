#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][uri]$WarehouseUrl,
    [uri]$CatalogueUrl = $env:WAREHOUSE_CATALOGUE_URL,
    [ValidateSet('BEFORE','AFTER')][string]$Phase = 'BEFORE',
    [string]$BeforeReport,
    [ValidatePattern('^[A-Za-z0-9_.-]+$')][string]$MySqlLoginPath,
    [string]$OutputDirectory = 'C:\Users\Admin\CarPot-Diagnostics',
    [switch]$NoPrompt
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
foreach ($origin in @($WarehouseUrl, $CatalogueUrl)) {
    if ($null -eq $origin) { continue }
    if (!$origin.IsAbsoluteUri -or $origin.UserInfo -or $origin.Query -or $origin.Fragment -or
        $origin.AbsolutePath -ne '/' -or ($origin.Scheme -ne 'https' -and !($origin.IsLoopback -and $origin.Scheme -eq 'http'))) {
        throw 'Use an HTTPS origin or an HTTP loopback origin, without a path or credentials.'
    }
}

function LocalSecret([string]$Variable, [string]$Label) {
    $value = [Environment]::GetEnvironmentVariable($Variable)
    if ($value -or $NoPrompt) { return $value }
    $secure = Read-Host $Label -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        $secure.Dispose()
    }
}

$cookie = LocalSecret 'WAREHOUSE_SESSION_COOKIE' 'Existing Warehouse session cookie value (local only)'
if (!$cookie -or $cookie -notmatch '^[A-Za-z0-9_.~-]+$') { throw 'A valid warehouse_session value is required.' }
$warehouseHeaders = @{}
$warehouseSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$warehouseSession.Cookies.Add($WarehouseUrl, (New-Object Net.Cookie('warehouse_session',$cookie,'/')))
$catalogueHeaders = @{}
if ($CatalogueUrl) {
    $key = LocalSecret 'WAREHOUSE_CATALOGUE_KEY' 'Existing Catalogue read key (local only)'
    if ($key) { $catalogueHeaders['X-Catalogue-Key'] = $key }
}

function Get-CarPot([uri]$Origin, [string]$Path, [hashtable]$Headers, [hashtable]$Query = @{}) {
    $pairs = @(foreach ($name in $Query.Keys) {
        foreach ($value in @($Query[$name])) {
            '{0}={1}' -f [uri]::EscapeDataString($name), [uri]::EscapeDataString([string]$value)
        }
    })
    $url = $Origin.AbsoluteUri.TrimEnd('/') + '/api/v1/' + $Path
    if ($pairs.Count) { $url += '?' + ($pairs -join '&') }
    try {
        $options = @{ Method='Get'; Uri=$url; Headers=$Headers; TimeoutSec=45; MaximumRedirection=0 }
        if ($Path.StartsWith('vehicles/vin/')) { $options['WebSession'] = $warehouseSession }
        $options['UseBasicParsing'] = $true
        $response = Invoke-WebRequest @options
        $stream = $response.RawContentStream
        $stream.Position = 0
        $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8, $true)
        try { $reader.ReadToEnd() | ConvertFrom-Json }
        finally { $reader.Dispose() }
    } catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'transport_error' }
        $detail = ''
        try {
            $raw = $_.ErrorDetails.Message
            if ($raw) {
                $value = ($raw | ConvertFrom-Json).detail
                if ($value -is [string]) { $detail = $value.Substring(0,[Math]::Min(240,$value.Length)) }
                elseif ($value) {
                    $detail = @($value | ForEach-Object { ($_.loc -join '.') + ' ' + $_.type }) -join ', '
                }
            }
        } catch { }
        throw "$Path ($status) $detail"
    }
}

function Read-Pages([string]$Path, [hashtable]$Headers, [hashtable]$Query, [int]$Cap = 100) {
    $rows = New-Object 'System.Collections.Generic.List[object]'
    $cursor = 0
    for ($i=0; $i -lt $Cap; $i++) {
        $Query['after'] = $cursor
        $page = Get-CarPot $WarehouseUrl $Path $Headers $Query
        if (!$page.PSObject.Properties['items']) { throw "$Path (unexpected response)" }
        if ($Path -eq 'vehicles/vin/resolution' -and $page.status -eq 'unavailable') {
            throw "$Path (source unavailable; count unknown)"
        }
        foreach ($row in $page.items) { $rows.Add($row) }
        if ($null -eq $page.next_after) { return $rows.ToArray() }
        if ([long]$page.next_after -le $cursor) { throw "$Path (invalid cursor)" }
        $cursor = [long]$page.next_after
    }
    throw "$Path (page limit reached; count unknown)"
}

function Pick-Row([string]$Label, [object[]]$Rows, [string]$Display) {
    if ($NoPrompt -or !$Rows.Count) { return $null }
    Write-Host "$Label (blank skips)"
    for ($i=0; $i -lt $Rows.Count; $i++) {
        $row = $Rows[$i]
        Write-Host ('  {0}. {1} [{2}] {3}' -f ($i+1), $row.$Display, $row.id, $row.construction_interval)
    }
    $index = 0
    $answer = Read-Host 'Number'
    if ([int]::TryParse($answer,[ref]$index) -and $index -ge 1 -and $index -le $Rows.Count) {
        return $Rows[$index-1]
    }
}

function Measure-Graph($Result) {
    if (!$catalogueHeaders.Count) { $Result.graph_status = 'catalogue_credentials_unavailable'; return }
    $identity = @{ kind=$Result.namespace; manufacturer_id=$Result.manufacturer_id
        model_id=$Result.model_id; car_id=$Result.modification_id }
    $graph = Get-CarPot $CatalogueUrl 'vehicles/source-graph' $catalogueHeaders $identity
    foreach ($field in $identity.Keys) {
        if ([string]$graph.identity.$field -ne [string]$identity[$field]) { throw 'source-graph (identity mismatch)' }
    }
    $Result.graph_status = $graph.status
    $Result.graph_reason = $graph.reason
    if ($graph.status -ne 'available') {
        if ($graph.status -in @('absent','unsupported','unverified')) { $Result.catalogue_mode = 'base_only' }
        return
    }
    if ($Result.namespace -ne 'passenger' -or $graph.source_scope -ne 'passenger_prd_article_oem') {
        throw 'source-graph (unexpected provenance)'
    }
    $plan = $graph.plan.payload
    if ($plan.car_id -ne $Result.modification_id -or $plan.model_id -ne $Result.model_id -or
        $plan.manufacturer_id -ne $Result.manufacturer_id -or $plan.source_snapshot_sha -cnotmatch '^[a-f0-9]{64}$') {
        throw 'source-graph (unexpected snapshot)'
    }
    $Result.snapshot_sha = $plan.source_snapshot_sha
    $products = @($plan.categories | Where-Object { $_.article_count -gt 0 })
    $planned = @($products | Where-Object { $_.source_fitment_linked -eq $true -and $_.kind -ne 'equipment' })
    $Result.prd_count = @($plan.categories | Select-Object -ExpandProperty product_id -Unique).Count
    $Result.plan_positions = $planned.Count
    $Result.catalogue_mode = if ($plan.coverage -eq 'complete_verified' -and $plan.coverage_verified -eq $true -and
        $plan.taxonomy_status -eq 'reviewed' -and $planned.Count -eq @($plan.categories).Count) { 'full' }
        elseif ($planned.Count) { 'partial' } else { 'base_only' }
    $articleKeys = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $oemKeys = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $plannedIds = @($planned | Select-Object -ExpandProperty product_id)
    $withOem = 0
    for ($offset=0; $offset -lt $products.Count;) {
        if ($products[$offset].article_count -gt 3000) { throw 'articles (single PRD exceeds 3000 links)' }
        $batch = @()
        $links = 0
        while ($offset -lt $products.Count -and $batch.Count -lt 12 -and
                $links + $products[$offset].article_count -le 3000) {
            $batch += $products[$offset]
            $links += $products[$offset].article_count
            $offset++
        }
        $articles = Get-CarPot $CatalogueUrl ("vehicles/{0}/article-batch" -f $Result.modification_id) $catalogueHeaders @{
            snapshot_sha=$Result.snapshot_sha; product_id=@($batch | Select-Object -ExpandProperty product_id)
        }
        if ($articles.snapshot_sha -cne $Result.snapshot_sha -or $articles.car_id -ne $Result.modification_id -or
            $articles.fitment -ne 'source_modification_link') { throw 'article-batch (snapshot or identity mismatch)' }
        foreach ($product in $batch) {
            $property = $articles.items.PSObject.Properties[[string]$product.product_id]
            if (!$property -or @($property.Value).Count -ne $product.article_count) { throw 'article-batch (partial result)' }
            $hasOem = $false
            $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
            foreach ($article in $property.Value) {
                if ($article.car_id -ne $Result.modification_id -or !$article.article_number -or !$article.supplier_id) {
                    throw 'article-batch (article identity mismatch)'
                }
                $articleKey = '{0}:{1}' -f $article.supplier_id,$article.article_number
                if (!$seen.Add($articleKey)) { throw 'article-batch (duplicate article)' }
                $null = $articleKeys.Add($articleKey)
                foreach ($oem in $article.oem) {
                    if ($oem.manufacturerId -eq $Result.manufacturer_id -and ([string]$oem.OENbr).Trim()) {
                        $null = $oemKeys.Add(('{0}:{1}' -f $oem.manufacturerId,([string]$oem.OENbr).Trim()))
                        $hasOem = $true
                    }
                }
            }
            if ($hasOem -and $product.product_id -in $plannedIds) { $withOem++ }
        }
    }
    $Result.article_count = $articleKeys.Count
    $Result.oem_count = $oemKeys.Count
    $Result.plan_positions_with_oem = $withOem
    if ($planned.Count) { $Result.oem_coverage_pct = [math]::Round(100.0 * $withOem / $planned.Count,2) }
}

# Optional source investigation uses an existing read-only MySQL login path.
# The published graph remains the only source for plan/OEM coverage metrics.
function Read-SourceSql([string]$Sql) {
    $lines = @(& mysql.exe "--login-path=$MySqlLoginPath" --database=td1q2018 --batch --skip-column-names "--execute=$Sql" 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'local MySQL SELECT failed' }
    return $lines
}

function Measure-LocalSource($Result) {
    if (!$MySqlLoginPath) { return }
    if ($Result.namespace -ne 'passenger') { $Result.local_source_status='commercial_link_type_unverified'; return }
    $metadata = @(Read-SourceSql "SELECT LOWER(CONCAT(TABLE_NAME,'.',COLUMN_NAME)) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('passanger_cars','passenger_cars','article_links','article_oe','prd')")
    $carTable = @('passanger_cars','passenger_cars') | Where-Object {
        "$_.id" -in $metadata -and "$_.modelid" -in $metadata
    } | Select-Object -First 1
    $required = @('article_links.linkageid','article_links.linkagetypeid','article_links.productid',
        'article_links.supplierid','article_links.datasupplierarticlenumber','prd.id',
        'article_oe.supplierid','article_oe.datasupplierarticlenumber','article_oe.manufacturerid','article_oe.oenbr')
    if (!$carTable -or @($required | Where-Object { $_ -notin $metadata }).Count) {
        $Result.local_source_status='schema_mismatch'; return
    }
    $indexes = @(Read-SourceSql "SELECT LOWER(CONCAT(TABLE_NAME,'.',COLUMN_NAME)) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND SEQ_IN_INDEX=1 AND TABLE_NAME IN ('article_links','article_oe')")
    if ('article_links.linkageid' -notin $indexes -or
        !@($indexes | Where-Object { $_ -in @('article_oe.supplierid','article_oe.manufacturerid','article_oe.datasupplierarticlenumber') }).Count) {
        $Result.local_source_status='index_preflight_failed'; return
    }
    $id = [long]$Result.modification_id
    $model = [long]$Result.model_id
    $maker = [long]$Result.manufacturer_id
    $car = @(Read-SourceSql "SELECT id FROM $carTable WHERE id=$id AND modelid=$model LIMIT 2")
    if ($car.Count -ne 1) { $Result.local_source_status='passenger_model_edge_missing'; return }

    $metrics = @(Read-SourceSql @"
SELECT /*+ MAX_EXECUTION_TIME(8000) */ COUNT(DISTINCT p.id),
       COUNT(DISTINCT l.supplierid, l.datasupplierarticlenumber),
       COUNT(DISTINCT CASE WHEN o.OENbr <> '' THEN o.OENbr END),
       COUNT(DISTINCT CASE WHEN o.OENbr <> '' THEN p.id END)
FROM article_links AS l JOIN prd AS p ON p.id=l.productid
LEFT JOIN article_oe AS o
 ON o.supplierId=l.supplierid AND o.DataSupplierArticleNumber=l.datasupplierarticlenumber
 AND o.manufacturerId=$maker
WHERE l.linkageid=$id AND l.linkagetypeid=2
"@)
    $values = ([string]$metrics[0]).Split("`t")
    if ($values.Count -ne 4 -or @($values | Where-Object { $_ -notmatch '^\d+$' }).Count) {
        throw 'local MySQL metrics response incomplete'
    }
    $Result.local_prd_count=[long]$values[0]
    $Result.local_article_count=[long]$values[1]
    $Result.local_oem_count=[long]$values[2]
    $Result.local_prd_with_oem_reference=[long]$values[3]
    $Result.local_source_status=if ($Result.local_prd_count) { 'linked_prd_present' } else { 'no_joined_prd' }
}

# Repository checkpoint records the public provenance for each VIN.
$sample = @(
    'WBAWB73549P045741|BMW|335i|passenger',
    'WAUUL78E78A124660|Audi|S4|passenger',
    'WVWDC21JX1W158839|Volkswagen|GTI|passenger',
    'WDDHH8JB5EA971934|Mercedes-Benz|E-Class|passenger',
    'YV4A22PK5G1081029|Volvo|XC90|passenger',
    'JT3FJ62G9K1100779|Toyota|Land Cruiser|passenger',
    'VF1RJB00067926560|Renault|Captur|passenger',
    '1FAFP42X3WF184546|Ford|Mustang|passenger',
    'XLRASH4300G220293|DAF|XF|commercial',
    'WMAT72ZZZ1L027315|MAN|33.604|commercial'
)

$prior = @{}
if ($BeforeReport) {
    foreach ($row in (Get-Content -LiteralPath $BeforeReport -Raw | ConvertFrom-Json).results) {
        $prior[$row.vin] = $row
    }
}

$results = @(for ($i=0; $i -lt $sample.Count; $i++) {
    $vin, $expectedMake, $label, $kind = $sample[$i].Split('|')
    Write-Progress -Activity 'CarPot Stage 13 VIN audit' -Status "$($i+1)/10 $expectedMake $label" -PercentComplete (10*$i)
    Write-Host "[$($i+1)/10] $vin $expectedMake $label ($kind)"
    $row = [ordered]@{
        phase=$Phase; vin=$vin; public_vehicle="$expectedMake $label"; namespace=$kind
        decoder_make=$null; decoder_model=$null; decoder_year=$null; characteristics=$null; provider_status=$null
        manufacturer_id=$null; model_id=$null; chosen_model=$null; modification_id=$null; chosen_modification=$null; chosen_identity_basis=$null
        maker_complete=$null; model_count=$null; strict_initial_model_count=$null
        strict_status=$null; strict_initial_count=$null; strict_initial_complete=$null
        strict_scoped_status=$null; strict_scoped_count=$null; catalogue_only_count=$null
        prd_count=$null; article_count=$null; oem_count=$null; plan_positions=$null
        plan_positions_with_oem=$null; oem_coverage_pct=$null; graph_status=$null
        warehouse_graph_status=$null; graph_reason=$null; catalogue_mode=$null; snapshot_sha=$null
        missing_fields=$null; decoder_conflicts=$null; observed_filter_gap=$null
        local_source_status=$null; local_prd_count=$null; local_article_count=$null; local_oem_count=$null; local_prd_with_oem_reference=$null
        add_and_dismantle='not_executed_read_only'; errors=@()
    }
    $decode = $null
    $headers = $null
    try {
        $decode = Get-CarPot $WarehouseUrl 'vehicles/vin/decode' $warehouseHeaders @{vin=$vin}
        $row.decoder_make = $decode.vehicle.manufacturer
        $row.decoder_model = $decode.vehicle.model
        $row.decoder_year = $decode.vehicle.year
        $row.characteristics = $decode.vehicle
        $row.provider_status = $decode.provider_status
        $row.missing_fields = $decode.missing_fields
        $row.decoder_conflicts = $decode.consistency_issues
        if (!$decode.resolution_context) { throw 'decode (Stage 13 context unavailable)' }
        $headers = @{ 'X-Vin-Context'=$decode.resolution_context }
        $initial = Get-CarPot $WarehouseUrl 'vehicles/vin/resolution' $headers
        $row.strict_initial_count = @($initial.items | Where-Object { $_ }).Count
        $row.strict_initial_model_count = @($initial.models | Where-Object { $_ }).Count
        $row.strict_initial_complete = $initial.search_complete
        $row.strict_status = $initial.status
    } catch { $row.errors += $_.Exception.Message }

    try {
        $makerData = Get-CarPot $WarehouseUrl 'vehicles/vin/source-manufacturers' $warehouseHeaders @{manufacturer=$expectedMake}
        $row.maker_complete = !$makerData.partial
        $makers = @($makerData.items | Where-Object { $_.kind -eq $kind } | ForEach-Object {
            [pscustomobject]@{ id=$_.manufacturer_id; name=$_.manufacturer }
        })
        if (!$makers.Count) { throw "manufacturer (no exact $kind match)" }
        $old = $prior[$vin]
        $maker = if ($old.manufacturer_id) { $makers | Where-Object { $_.id -eq $old.manufacturer_id } | Select-Object -First 1 }
        if (!$maker) {
            $maker = if ($makers.Count -eq 1) { $makers[0] } else { Pick-Row 'Choose manufacturer' $makers 'name' }
        }
        if ($maker) {
            $row.manufacturer_id = $maker.id
            $models = @(Read-Pages 'vehicles/vin/source-models' $warehouseHeaders @{manufacturer_id=$maker.id; kind=$kind})
            $row.model_count = $models.Count
            $model = if ($NoPrompt -and $old.model_id) { $models | Where-Object { $_.id -eq $old.model_id } | Select-Object -First 1 }
            if (!$model) {
                $matches = @($models | Where-Object { $_.name -eq $label -or $_.name -eq $row.decoder_model })
                $model = if ($matches.Count -eq 1) { $matches[0] } else { Pick-Row "Choose the source model for $label" $models 'name' }
            }
            if ($model) {
                $row.model_id = $model.id
                $row.chosen_model = $model.name
                $variants = @(Read-Pages 'vehicles/vin/source-modifications' $warehouseHeaders @{model_id=$model.id; kind=$kind})
                $row.catalogue_only_count = $variants.Count
                $strict = @()
                if ($headers) {
                    try {
                        $query = @{maker=($kind + ':' + $maker.id); model_id=$model.id; after=0}
                        $strictPage = Get-CarPot $WarehouseUrl 'vehicles/vin/resolution' $headers $query
                        $row.strict_scoped_status = $strictPage.status
                        $strict = @(Read-Pages 'vehicles/vin/resolution' $headers $query |
                            Where-Object { $_.model_id -eq $model.id -and $_.manufacturer_id -eq $maker.id -and $_.kind -eq $kind } |
                            Sort-Object source_modification_id -Unique)
                        $row.strict_scoped_count = $strict.Count
                        $row.observed_filter_gap = $variants.Count - $strict.Count
                    } catch { $row.errors += $_.Exception.Message }
                }
                $variant = if ($NoPrompt -and $old.modification_id) { $variants | Where-Object { $_.id -eq $old.modification_id } | Select-Object -First 1 }
                if (!$variant) { $variant = Pick-Row 'Choose the modification only if independently identified' $variants 'name' }
                if ($variant) {
                    $row.modification_id = $variant.id
                    $row.chosen_identity_basis = if ($NoPrompt) { 'reused_before_diagnostic_candidate' } else { 'operator_diagnostic_candidate' }
                    $row.chosen_modification = $variant.name
                    $signed = $strict | Where-Object { $_.source_modification_id -eq $variant.id } | Select-Object -First 1
                    if ($signed.choice) {
                        try {
                            $graphHeaders = $headers.Clone()
                            $graphHeaders['X-Vin-Choice'] = $signed.choice
                            $ready = Get-CarPot $WarehouseUrl 'vehicles/vin/resolution-graph' $graphHeaders
                            $row.warehouse_graph_status = $ready.status
                        } catch { $row.errors += $_.Exception.Message }
                    }
                    try { Measure-Graph $row } catch { $row.errors += $_.Exception.Message }
                    Measure-LocalSource $row
                }
            }
        }
    } catch { $row.errors += $_.Exception.Message }
    [pscustomobject]$row
})
Write-Progress -Activity 'CarPot Stage 13 VIN audit' -Completed
$null = New-Item -ItemType Directory -Path $OutputDirectory -Force
$prefix = Join-Path $OutputDirectory ("stage13-{0}-{1}" -f $Phase,(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
[ordered]@{ captured_at=(Get-Date).ToString('o'); phase=$Phase; results=$results } |
    ConvertTo-Json -Depth 20 | Set-Content -LiteralPath "$prefix.json" -Encoding UTF8
$columns = @('phase','vin','public_vehicle','namespace','decoder_make','decoder_model','decoder_year',
    'manufacturer_id','model_count','strict_initial_model_count','strict_initial_count','strict_initial_complete',
    'strict_status','strict_scoped_count','strict_scoped_status','catalogue_only_count','observed_filter_gap',
    'model_id','chosen_model','modification_id','chosen_modification','chosen_identity_basis','prd_count','article_count',
    'oem_count','plan_positions','plan_positions_with_oem','oem_coverage_pct','graph_status',
    'warehouse_graph_status','graph_reason','catalogue_mode','snapshot_sha','add_and_dismantle',
    'local_source_status','local_prd_count','local_article_count','local_oem_count','local_prd_with_oem_reference',
    @{Name='errors';Expression={$_.errors -join '; '}})
$combined = @(foreach ($item in $results) {
    if ($prior.ContainsKey($item.vin)) { $prior[$item.vin] }
    $item
})
$combined | Select-Object -Property $columns | Export-Csv -LiteralPath "$prefix.csv" -Encoding UTF8 -NoTypeInformation
$combined | Select-Object -Property $columns | Format-List | Out-String -Width 180 |
    Set-Content -LiteralPath "$prefix.txt" -Encoding UTF8
Write-Host "Reports saved: $prefix (.json, .csv, .txt)"
