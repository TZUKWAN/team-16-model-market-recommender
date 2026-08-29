[CmdletBinding()]
param(
    [string]$OutputDirectory = '',
    [switch]$AllowDirty,
    [switch]$KeepStaging
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $Root 'dist'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$ModelDirectory = Join-Path $Root 'data\models\bge-m3'
$ManifestPath = Join-Path $Root 'data\models\bge-m3.manifest.json'
$Verifier = Join-Path $Root 'scripts\verify-delivery.ps1'
$Comparator = Join-Path $Root 'scripts\compare-delivery-to-source.ps1'
$ZipCreator = Join-Path $Root 'scripts\create_zip64.py'

function Invoke-Git {
    param([string[]]$GitArguments)
    $output = & git -C $Root @GitArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($GitArguments -join ' ')"
    }
    return $output
}

function Remove-SafeDirectory {
    param(
        [string]$Path,
        [string]$AllowedRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $pathFull = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $allowedFull = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\', '/')
    $prefix = $allowedFull + [IO.Path]::DirectorySeparatorChar
    if (
        $pathFull -eq $allowedFull -or
        -not $pathFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Refusing to remove a directory outside the packaging root: $pathFull"
    }
    Remove-Item -LiteralPath $pathFull -Recurse -Force
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Required command is unavailable: git'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Required command is unavailable: python'
}
if (-not (Test-Path -LiteralPath $ModelDirectory -PathType Container)) {
    throw "BGE-M3 model directory is missing: $ModelDirectory"
}
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "BGE-M3 manifest is missing: $ManifestPath"
}

$statusLines = @(Invoke-Git -GitArguments @('status', '--porcelain'))
if ($statusLines.Count -gt 0 -and -not $AllowDirty) {
    throw (
        "The source worktree is not clean. Commit or review the intended delivery " +
        "changes, then rerun; use -AllowDirty only for a review candidate."
    )
}

$commit = ([string](Invoke-Git -GitArguments @('rev-parse', 'HEAD'))).Trim()
$branch = ([string](Invoke-Git -GitArguments @('branch', '--show-current'))).Trim()
$shortCommit = $commit.Substring(0, 8)
$packageName = "team-16-competition-bge-m3-$shortCommit"
$stagingParent = Join-Path $OutputDirectory 'staging'
$packageRoot = Join-Path $stagingParent $packageName
$extractParent = Join-Path $OutputDirectory 'verification-extract'
$zipPath = Join-Path $OutputDirectory "$packageName.zip"
$sourceReport = Join-Path $OutputDirectory "$packageName-source-verification.json"
$extractedReport = Join-Path $OutputDirectory "$packageName-extracted-verification.json"
$parityReport = Join-Path $OutputDirectory "$packageName-source-parity.json"
$hashPath = "$zipPath.sha256"

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
Remove-SafeDirectory -Path $stagingParent -AllowedRoot $OutputDirectory
Remove-SafeDirectory -Path $extractParent -AllowedRoot $OutputDirectory
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
if (Test-Path -LiteralPath $hashPath) {
    Remove-Item -LiteralPath $hashPath -Force
}
New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

Write-Host '[Team 16] Copying source files...'
$sourceFiles = @(
    Invoke-Git -GitArguments @(
        '-c', 'core.quotepath=false',
        'ls-files', '--cached', '--others', '--exclude-standard'
    )
)
foreach ($relativePath in $sourceFiles) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        continue
    }
    $sourcePath = Join-Path $Root $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        continue
    }
    $destinationPath = Join-Path $packageRoot $relativePath
    $destinationDirectory = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}

Write-Host '[Team 16] Copying BGE-M3 model artifact...'
$packagedModelParent = Join-Path $packageRoot 'data\models'
New-Item -ItemType Directory -Force -Path $packagedModelParent | Out-Null
Copy-Item `
    -LiteralPath $ModelDirectory `
    -Destination (Join-Path $packagedModelParent 'bge-m3') `
    -Recurse `
    -Force
Copy-Item `
    -LiteralPath $ManifestPath `
    -Destination (Join-Path $packagedModelParent 'bge-m3.manifest.json') `
    -Force

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$buildInfo = [ordered]@{
    delivery_format_version = 1
    source_branch = $branch
    source_commit = $commit
    source_worktree_dirty = $statusLines.Count -gt 0
    source_worktree_changes = $statusLines
    built_at = (Get-Date).ToUniversalTime().ToString('o')
    model_id = [string]$manifest.model_id
    model_revision = [string]$manifest.resolved_revision
    model_dimension = [int]$manifest.embedding_dimension
    model_file_count = @($manifest.files).Count
    model_total_bytes = [int64](
        @($manifest.files | Measure-Object -Property size -Sum).Sum
    )
}
$buildInfo |
    ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $packageRoot 'BUILD_INFO.json') -Encoding UTF8

Write-Host '[Team 16] Verifying staging content and all model checksums...'
& powershell.exe `
    -NoLogo `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $Verifier `
    -DeliveryRoot $packageRoot `
    -ReportPath $sourceReport `
    -ExpectedSourceCommit $commit `
    -RequireBuildInfo
if ($LASTEXITCODE -ne 0) {
    throw 'Staging delivery verification failed.'
}

Write-Host '[Team 16] Creating a Zip64 archive...'
& python $ZipCreator `
    --source-dir $packageRoot `
    --archive $zipPath `
    --root-name $packageName
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
    throw 'Zip64 archive creation failed.'
}

Write-Host '[Team 16] Extracting and re-verifying the archive...'
New-Item -ItemType Directory -Force -Path $extractParent | Out-Null
& python -m zipfile -t $zipPath
if ($LASTEXITCODE -ne 0) {
    throw 'Zip64 archive CRC verification failed.'
}
& python -m zipfile -e $zipPath $extractParent
if ($LASTEXITCODE -ne 0) {
    throw 'Archive extraction verification failed.'
}
$extractedRoot = Join-Path $extractParent $packageName
& powershell.exe `
    -NoLogo `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File (Join-Path $extractedRoot 'scripts\verify-delivery.ps1') `
    -DeliveryRoot $extractedRoot `
    -ReportPath $extractedReport `
    -ExpectedSourceCommit $commit `
    -RequireBuildInfo
if ($LASTEXITCODE -ne 0) {
    throw 'Extracted delivery verification failed.'
}

Write-Host '[Team 16] Comparing every tracked source path and SHA-256...'
$comparisonArguments = @(
    '-NoLogo',
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $Comparator,
    '-SourceRoot', $Root,
    '-DeliveryRoot', $extractedRoot,
    '-ReportPath', $parityReport
)
if ($AllowDirty) {
    $comparisonArguments += '-IncludeUntracked'
}
& powershell.exe @comparisonArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Delivery source parity verification failed.'
}

$archiveHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content `
    -LiteralPath $hashPath `
    -Encoding ASCII `
    -Value "$archiveHash  $([IO.Path]::GetFileName($zipPath))"

$result = [ordered]@{
    status = 'packaged'
    archive = $zipPath
    archive_bytes = (Get-Item -LiteralPath $zipPath).Length
    archive_sha256 = $archiveHash
    source_commit = $commit
    model_revision = [string]$manifest.resolved_revision
    model_included = $true
    tracked_source_parity = 'identical'
}
$result | ConvertTo-Json -Depth 5

if (-not $KeepStaging) {
    Remove-SafeDirectory -Path $stagingParent -AllowedRoot $OutputDirectory
    Remove-SafeDirectory -Path $extractParent -AllowedRoot $OutputDirectory
}
