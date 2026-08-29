[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$SourceRoot,

    [Parameter(Mandatory)]
    [string]$DeliveryRoot,

    [string]$ReportPath = '',

    [switch]$IncludeUntracked
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$SourceRoot = (Resolve-Path $SourceRoot).Path
$DeliveryRoot = (Resolve-Path $DeliveryRoot).Path

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Required command is unavailable: git'
}

$trackedFiles = @(
    & git -C $SourceRoot -c core.quotepath=false ls-files --cached
)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to list tracked source files.'
}
$sourceFiles = @($trackedFiles)
if ($IncludeUntracked) {
    $untrackedFiles = @(
        & git -C $SourceRoot -c core.quotepath=false `
            ls-files --others --exclude-standard
    )
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to list untracked source files.'
    }
    $sourceFiles += $untrackedFiles
}

$expectedPaths = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)
$missing = [Collections.Generic.List[string]]::new()
$mismatched = [Collections.Generic.List[object]]::new()

foreach ($relativePath in $sourceFiles) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        continue
    }
    $normalized = $relativePath.Replace('\', '/')
    [void]$expectedPaths.Add($normalized)
    $sourcePath = Join-Path $SourceRoot $relativePath
    $deliveryPath = Join-Path $DeliveryRoot $relativePath
    if (-not (Test-Path -LiteralPath $deliveryPath -PathType Leaf)) {
        $missing.Add($normalized)
        continue
    }
    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $deliveryHash = (Get-FileHash -LiteralPath $deliveryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sourceHash -ne $deliveryHash) {
        $mismatched.Add(
            [ordered]@{
                path = $normalized
                source_sha256 = $sourceHash
                delivery_sha256 = $deliveryHash
            }
        )
    }
}

$unexpected = [Collections.Generic.List[string]]::new()
$deliveryFiles = @(Get-ChildItem -LiteralPath $DeliveryRoot -Recurse -File -Force)
foreach ($file in $deliveryFiles) {
    $relativePath = $file.FullName.Substring($DeliveryRoot.Length).TrimStart('\', '/')
    $normalized = $relativePath.Replace('\', '/')
    $allowedExtra = (
        $normalized -eq 'BUILD_INFO.json' -or
        $normalized -eq 'data/models/bge-m3.manifest.json' -or
        $normalized.StartsWith('data/models/bge-m3/', [StringComparison]::Ordinal)
    )
    if (-not $expectedPaths.Contains($normalized) -and -not $allowedExtra) {
        $unexpected.Add($normalized)
    }
}

$status = if (
    $missing.Count -eq 0 -and
    $mismatched.Count -eq 0 -and
    $unexpected.Count -eq 0
) { 'identical' } else { 'different' }
$result = [ordered]@{
    status = $status
    source_root = $SourceRoot
    delivery_root = $DeliveryRoot
    tracked_source_file_count = $trackedFiles.Count
    compared_source_file_count = $expectedPaths.Count
    included_untracked_files = [bool]$IncludeUntracked
    delivery_file_count = $deliveryFiles.Count
    missing_tracked_files = @($missing)
    hash_mismatches = @($mismatched)
    unexpected_delivery_files = @($unexpected)
    allowed_delivery_extras = @(
        'BUILD_INFO.json',
        'data/models/bge-m3.manifest.json',
        'data/models/bge-m3/**'
    )
    compared_at = (Get-Date).ToUniversalTime().ToString('o')
}
$json = $result | ConvertTo-Json -Depth 8

if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
    $reportFullPath = [IO.Path]::GetFullPath($ReportPath)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportFullPath) | Out-Null
    Set-Content -LiteralPath $reportFullPath -Value $json -Encoding UTF8
}

Write-Output $json
if ($status -ne 'identical') {
    throw 'Delivery source parity verification failed.'
}
