[CmdletBinding()]
param(
    [string]$DeliveryRoot = '',
    [string]$ReportPath = '',
    [string]$ExpectedSourceCommit = '',
    [switch]$RequireBuildInfo,
    [switch]$SkipDockerConfig
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if ([string]::IsNullOrWhiteSpace($DeliveryRoot)) {
    $DeliveryRoot = Join-Path $PSScriptRoot '..'
}
$Root = (Resolve-Path $DeliveryRoot).Path
$ModelDirectory = Join-Path $Root 'data\models\bge-m3'
$ManifestPath = Join-Path $Root 'data\models\bge-m3.manifest.json'
$DenseComposePath = Join-Path $Root 'docker-compose.dense.yml'

function Assert-Path {
    param(
        [string]$RelativePath,
        [ValidateSet('Leaf', 'Container')]
        [string]$PathType = 'Leaf'
    )

    $path = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $path -PathType $PathType)) {
        throw "Required delivery path is missing: $RelativePath"
    }
}

function Get-SafeChildPath {
    param(
        [string]$Parent,
        [string]$RelativePath
    )

    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    $candidate = [IO.Path]::GetFullPath((Join-Path $parentFull $RelativePath))
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes the model directory: $RelativePath"
    }
    return $candidate
}

$requiredFiles = @(
    'start-competition.bat',
    'stop-competition.bat',
    'scripts\start-competition.ps1',
    'scripts\stop-competition.ps1',
    'scripts\verify-delivery.ps1',
    'scripts\package-competition.ps1',
    'scripts\compare-delivery-to-source.ps1',
    'scripts\create_zip64.py',
    'scripts\check_no_secret_leak.py',
    'docker-compose.yml',
    'docker-compose.dense.yml',
    'backend\Dockerfile',
    'frontend\Dockerfile',
    'data\official_60\models.jsonl',
    'reports\official\eval_official_results.json',
    'reports\official_eval\official_topk_summary.json',
    'reports\official_eval\val_results.json',
    'reports\official_eval\test_results.json',
    'reports\official_eval\official_failures.json',
    'reports\official_eval\official_topk_report.md',
    'MODEL_LICENSE.txt',
    'RUN_INSTRUCTIONS_ZH.txt'
)
foreach ($relativePath in $requiredFiles) {
    Assert-Path -RelativePath $relativePath
}
Assert-Path -RelativePath 'data\models\bge-m3' -PathType Container
Assert-Path -RelativePath 'data\models\bge-m3.manifest.json'
$buildInfo = $null
if ($RequireBuildInfo) {
    Assert-Path -RelativePath 'BUILD_INFO.json'
    $buildInfo = Get-Content `
        -LiteralPath (Join-Path $Root 'BUILD_INFO.json') `
        -Raw `
        -Encoding UTF8 |
        ConvertFrom-Json

    $requiredBuildFields = @(
        'source_commit',
        'source_worktree_dirty',
        'model_id',
        'model_revision',
        'model_dimension',
        'model_file_count',
        'model_total_bytes'
    )
    foreach ($field in $requiredBuildFields) {
        if ($buildInfo.PSObject.Properties.Name -notcontains $field) {
            throw "BUILD_INFO.json is missing required field: $field"
        }
    }
    if ([string]$buildInfo.source_commit -notmatch '^[0-9a-f]{40}$') {
        throw 'BUILD_INFO.json source_commit is not a full Git SHA.'
    }
    if ($buildInfo.source_worktree_dirty -isnot [bool]) {
        throw 'BUILD_INFO.json source_worktree_dirty must be a JSON boolean.'
    }
    if (
        -not [string]::IsNullOrWhiteSpace($ExpectedSourceCommit) -and
        [string]$buildInfo.source_commit -ne $ExpectedSourceCommit
    ) {
        throw (
            "BUILD_INFO.json source commit mismatch: expected " +
            "$ExpectedSourceCommit, got $($buildInfo.source_commit)"
        )
    }
}

$forbiddenPaths = @(
    '.git',
    '.env',
    'backend\.env',
    'frontend\.env',
    'node_modules',
    'frontend\node_modules',
    '.venv',
    '.delivery',
    'data\runtime',
    'logs',
    'output\playwright'
)
foreach ($relativePath in $forbiddenPaths) {
    $candidate = Join-Path $Root $relativePath
    if (Test-Path -LiteralPath $candidate) {
        throw "Forbidden local or secret-bearing path is present: $relativePath"
    }
}

$forbiddenDirectoryNames = @(
    '.git',
    '.venv',
    'node_modules',
    '.delivery',
    '__pycache__',
    '.pytest_cache'
)
$forbiddenDirectories = @(
    Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force |
        Where-Object { $_.Name -in $forbiddenDirectoryNames }
)
if ($forbiddenDirectories.Count -gt 0) {
    $names = $forbiddenDirectories.FullName -join ', '
    throw "Forbidden generated directories are present: $names"
}

$forbiddenSecretFiles = @(
    Get-ChildItem -LiteralPath $Root -Recurse -File -Force |
        Where-Object {
            (
                (
                    $_.Name -match '^\.env($|\.)' -and
                    $_.Name -notmatch '^\.env\.(example|sample|template)$'
                ) -or
                $_.Name -match '(\.pem$|\.p12$|\.pfx$|\.key$)'
            ) -and
            $_.FullName -notlike "$ModelDirectory*"
        }
)
if ($forbiddenSecretFiles.Count -gt 0) {
    $names = $forbiddenSecretFiles.FullName -join ', '
    throw "Potential secret-bearing files are present: $names"
}

$forbiddenRuntimeFiles = @(
    Get-ChildItem -LiteralPath $Root -Recurse -File -Force |
        Where-Object {
            $_.Extension -in @('.db', '.sqlite', '.sqlite3', '.log') -and
            $_.FullName -notlike "$ModelDirectory*"
        }
)
if ($forbiddenRuntimeFiles.Count -gt 0) {
    $names = $forbiddenRuntimeFiles.FullName -join ', '
    throw "Forbidden runtime files are present: $names"
}

$denseComposeText = Get-Content -LiteralPath $DenseComposePath -Raw -Encoding UTF8
$revisionMatches = [regex]::Matches(
    $denseComposeText,
    'BGE_M3_REVISION:-([0-9a-f]{40})'
)
$expectedModelRevisions = @(
    $revisionMatches |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
)
if ($expectedModelRevisions.Count -ne 1) {
    throw (
        'docker-compose.dense.yml must declare exactly one pinned ' +
        'BGE-M3 revision.'
    )
}
$expectedModelRevision = [string]$expectedModelRevisions[0]

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$manifest.schema_version -ne 1) {
    throw "Unsupported BGE-M3 manifest schema: $($manifest.schema_version)"
}
if ([string]$manifest.model_id -ne 'BAAI/bge-m3') {
    throw "Unexpected model id: $($manifest.model_id)"
}
if ([string]$manifest.resolved_revision -ne $expectedModelRevision) {
    throw (
        "Model revision mismatch: docker-compose.dense.yml pins " +
        "$expectedModelRevision, manifest contains $($manifest.resolved_revision)"
    )
}
if ([int]$manifest.embedding_dimension -ne 1024) {
    throw "Unexpected embedding dimension: $($manifest.embedding_dimension)"
}
if (@($manifest.files).Count -eq 0) {
    throw 'The BGE-M3 manifest does not list any model files.'
}

$manifestPaths = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
$totalBytes = [int64]0
foreach ($entry in $manifest.files) {
    $relativePath = [string]$entry.path
    if (-not $manifestPaths.Add($relativePath.Replace('\', '/'))) {
        throw "Duplicate model path in manifest: $relativePath"
    }

    $path = Get-SafeChildPath -Parent $ModelDirectory -RelativePath $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Model file listed by the manifest is missing: $relativePath"
    }

    $file = Get-Item -LiteralPath $path
    if ([int64]$file.Length -ne [int64]$entry.size) {
        throw "Model file size mismatch: $relativePath"
    }

    $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne ([string]$entry.sha256).ToLowerInvariant()) {
        throw "Model SHA-256 mismatch: $relativePath"
    }
    $totalBytes += [int64]$file.Length
}

$actualModelFiles = @(
    Get-ChildItem -LiteralPath $ModelDirectory -Recurse -File -Force
)
foreach ($file in $actualModelFiles) {
    $relativePath = $file.FullName.Substring($ModelDirectory.Length).TrimStart('\', '/')
    $normalized = $relativePath.Replace('\', '/')
    if (-not $manifestPaths.Contains($normalized)) {
        throw "Unmanifested model file is present: $normalized"
    }
}
if ($actualModelFiles.Count -ne $manifestPaths.Count) {
    throw "Model file count does not match the manifest."
}

if ($null -ne $buildInfo) {
    if ([string]$buildInfo.model_id -ne [string]$manifest.model_id) {
        throw 'BUILD_INFO.json model_id does not match the model manifest.'
    }
    if ([string]$buildInfo.model_revision -ne [string]$manifest.resolved_revision) {
        throw 'BUILD_INFO.json model_revision does not match the model manifest.'
    }
    if ([int]$buildInfo.model_dimension -ne [int]$manifest.embedding_dimension) {
        throw 'BUILD_INFO.json model_dimension does not match the model manifest.'
    }
    if ([int]$buildInfo.model_file_count -ne $manifestPaths.Count) {
        throw 'BUILD_INFO.json model_file_count does not match verified files.'
    }
    if ([int64]$buildInfo.model_total_bytes -ne $totalBytes) {
        throw 'BUILD_INFO.json model_total_bytes does not match verified bytes.'
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is required for delivery secret scanning.'
}
& python (Join-Path $Root 'scripts\check_no_secret_leak.py')
if ($LASTEXITCODE -ne 0) {
    throw 'Delivery content secret scan failed.'
}

if (-not $SkipDockerConfig) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker is required for Compose configuration validation.'
    }
    & docker compose `
        -f (Join-Path $Root 'docker-compose.yml') `
        -f (Join-Path $Root 'docker-compose.dense.yml') `
        config `
        --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed with exit code $LASTEXITCODE."
    }
}

$result = [ordered]@{
    status = 'verified'
    delivery_root = $Root
    model_id = [string]$manifest.model_id
    model_revision = [string]$manifest.resolved_revision
    model_dimension = [int]$manifest.embedding_dimension
    model_file_count = $manifestPaths.Count
    model_total_bytes = $totalBytes
    expected_source_commit = $ExpectedSourceCommit
    build_info_verified = $null -ne $buildInfo
    secret_scan_verified = $true
    docker_config_verified = -not $SkipDockerConfig
    verified_at = (Get-Date).ToUniversalTime().ToString('o')
}
$json = $result | ConvertTo-Json -Depth 5

if (-not [string]::IsNullOrWhiteSpace($ReportPath)) {
    $reportFullPath = [IO.Path]::GetFullPath($ReportPath)
    $reportDirectory = Split-Path -Parent $reportFullPath
    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    Set-Content -LiteralPath $reportFullPath -Value $json -Encoding UTF8
}

Write-Output $json
