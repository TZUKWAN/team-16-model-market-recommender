[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,

    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000,

    [ValidateRange(60, 1800)]
    [int]$StartupTimeoutSeconds = 600,

    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BaseCompose = Join-Path $Root 'docker-compose.yml'
$DenseCompose = Join-Path $Root 'docker-compose.dense.yml'
$ModelDirectory = Join-Path $Root 'data\models\bge-m3'
$ModelManifest = Join-Path $Root 'data\models\bge-m3.manifest.json'
$DeliveryDirectory = Join-Path $Root '.delivery'
$LogDirectory = Join-Path $DeliveryDirectory 'logs'
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$TranscriptPath = Join-Path $LogDirectory "start-$Timestamp.log"
$TranscriptStarted = $false

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "[Team 16] $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is unavailable: $Name"
    }
}

function Assert-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required delivery file is missing: $Path"
    }
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory)]
        [string[]]$ComposeArguments
    )

    $dockerArguments = @(
        'compose',
        '-f', $BaseCompose,
        '-f', $DenseCompose
    ) + $ComposeArguments

    Write-Host ("docker " + ($dockerArguments -join ' ')) -ForegroundColor DarkGray
    & docker @dockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose command failed with exit code $LASTEXITCODE."
    }
}

function Show-Diagnostics {
    Write-Host ""
    Write-Host "[Team 16] Docker diagnostics:" -ForegroundColor Yellow
    try {
        & docker compose -f $BaseCompose -f $DenseCompose ps
        & docker compose -f $BaseCompose -f $DenseCompose logs --tail 120 backend frontend
    } catch {
        Write-Warning "Unable to collect Docker diagnostics: $($_.Exception.Message)"
    }
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null

try {
    Start-Transcript -LiteralPath $TranscriptPath -Force | Out-Null
    $TranscriptStarted = $true

    Write-Step "Checking the delivery package and Docker runtime"
    Assert-Command 'docker'
    Assert-File $BaseCompose
    Assert-File $DenseCompose
    Assert-File (Join-Path $Root 'backend\Dockerfile')
    Assert-File (Join-Path $Root 'frontend\Dockerfile')
    Assert-File (Join-Path $Root 'data\official_60\models.jsonl')
    Assert-File (Join-Path $Root 'reports\official_eval\official_topk_summary.json')
    Assert-File (Join-Path $Root 'reports\official_eval\val_results.json')
    Assert-File (Join-Path $Root 'reports\official_eval\test_results.json')
    Assert-File (Join-Path $Root 'reports\official_eval\official_failures.json')
    Assert-File (Join-Path $Root 'reports\official_eval\official_topk_report.md')

    $serverVersion = & docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serverVersion)) {
        throw "Docker Desktop is not running or the current user cannot access Docker."
    }
    Write-Host "Docker Engine: $serverVersion"

    $env:BACKEND_PORT = [string]$BackendPort
    $env:FRONTEND_PORT = [string]$FrontendPort
    $env:VITE_API_BASE_URL = "http://localhost:$BackendPort"
    $env:CORS_ORIGINS = (
        "http://localhost:$FrontendPort," +
        "http://127.0.0.1:$FrontendPort"
    )

    Invoke-Compose -ComposeArguments @('config', '--quiet')

    $modelExists = Test-Path -LiteralPath $ModelDirectory -PathType Container
    $manifestExists = Test-Path -LiteralPath $ModelManifest -PathType Leaf
    if ($modelExists -xor $manifestExists) {
        throw (
            "The BGE-M3 artifact is incomplete. The model directory and manifest " +
            "must either both exist or both be absent. Restore the delivery package " +
            "before retrying."
        )
    }

    if ($modelExists) {
        Write-Step "Verifying the packaged BGE-M3 artifact"
    } else {
        Write-Step "BGE-M3 is absent; downloading the pinned artifact"
    }
    Invoke-Compose -ComposeArguments @(
        '--profile', 'prepare',
        'run', '--build', '--rm',
        'dense-model-prepare'
    )

    Write-Step "Building and starting the competition-dense stack"
    Invoke-Compose -ComposeArguments @('up', '--build', '-d', 'backend', 'frontend')

    Write-Step "Waiting for BGE-M3 and the backend health gate"
    $backendUrl = "http://127.0.0.1:$BackendPort"
    $frontendUrl = "http://127.0.0.1:$FrontendPort"
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $health = $null
    $lastReason = 'health endpoint has not responded'

    while ((Get-Date) -lt $deadline) {
        try {
            $candidate = Invoke-RestMethod `
                -Uri "$backendUrl/api/v1/health" `
                -Method Get `
                -TimeoutSec 10

            $checks = @(
                ($candidate.status -eq 'healthy')
                ($candidate.retrieval_runtime_mode -eq 'competition_dense')
                ([bool]$candidate.dense_available)
                ([bool]$candidate.dense_manifest_verified)
                ([int]$candidate.dense_embedding_dimension -eq 1024)
                ([bool]$candidate.dense_offline)
            )
            if ($checks -notcontains $false) {
                $health = $candidate
                break
            }

            $lastReason = (
                "status={0}, mode={1}, dense_available={2}, manifest={3}, dimension={4}, offline={5}" -f
                $candidate.status,
                $candidate.retrieval_runtime_mode,
                $candidate.dense_available,
                $candidate.dense_manifest_verified,
                $candidate.dense_embedding_dimension,
                $candidate.dense_offline
            )
        } catch {
            $lastReason = $_.Exception.Message
        }
        Start-Sleep -Seconds 5
    }

    if ($null -eq $health) {
        Show-Diagnostics
        throw "Competition health gate did not pass within $StartupTimeoutSeconds seconds: $lastReason"
    }

    Write-Step "Checking the frontend"
    $frontendResponse = Invoke-WebRequest `
        -Uri "$frontendUrl/" `
        -UseBasicParsing `
        -TimeoutSec 15
    if ($frontendResponse.StatusCode -ne 200) {
        throw "Frontend returned HTTP $($frontendResponse.StatusCode), expected 200."
    }

    Write-Step "Competition runtime is ready"
    Write-Host "Frontend: $frontendUrl"
    Write-Host "Backend:  $backendUrl"
    Write-Host "Mode:     $($health.retrieval_runtime_mode)"
    Write-Host "BGE-M3:   available=$($health.dense_available), dimension=$($health.dense_embedding_dimension)"
    Write-Host "Manifest: verified=$($health.dense_manifest_verified)"
    Write-Host "Log:      $TranscriptPath"

    if (-not $NoBrowser) {
        Start-Process $frontendUrl
    }
} catch {
    Write-Host ""
    Write-Host "[Team 16] Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "[Team 16] Log: $TranscriptPath" -ForegroundColor Yellow
    exit 1
} finally {
    if ($TranscriptStarted) {
        Stop-Transcript | Out-Null
    }
}

exit 0
