[CmdletBinding()]
param(
    [int]$BackendPort = 8010,
    [int]$FrontendPort = 5173,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RunDir = Join-Path $Root '.codex\run'
$LogDir = Join-Path $Root '.codex\logs'
$StatePath = Join-Path $RunDir 'project-processes.json'

function Normalize-ProcessPathEnvironment {
    if ($env:OS -ne 'Windows_NT') { return }

    $pathKeys = @(
        [Environment]::GetEnvironmentVariables('Process').Keys |
            Where-Object { $_ -ieq 'PATH' }
    )
    if ($pathKeys.Count -lt 2) { return }

    $pathValues = @(
        foreach ($key in $pathKeys) {
            $value = [Environment]::GetEnvironmentVariable([string]$key, 'Process')
            if (-not [string]::IsNullOrWhiteSpace($value)) { $value }
        }
    ) | Select-Object -Unique

    [Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable(
        'Path',
        ($pathValues -join [IO.Path]::PathSeparator),
        'Process'
    )
}

Normalize-ProcessPathEnvironment

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is unavailable: $Name"
    }
}

function Assert-PortFree([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is already owned by PID $($listener.OwningProcess). Run status-project.ps1 before retrying."
    }
}

Assert-Command 'python'
Assert-Command 'node'
Assert-Command 'npm.cmd'
Assert-PortFree $BackendPort
Assert-PortFree $FrontendPort

$required = @(
    'backend\app\main.py',
    'frontend\node_modules\vite\bin\vite.js',
    'data\official\questions_all.jsonl',
    'data\official\model_catalog_structured.jsonl',
    'data\config\recommendation_weights.json'
)
foreach ($relative in $required) {
    if (-not (Test-Path (Join-Path $Root $relative))) {
        throw "Required project asset is missing: $relative"
    }
}

& python -c "import fastapi,httpx,pydantic,sqlite3; print('Backend dependency check: OK')"
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency check failed.' }

New-Item -ItemType Directory -Force $RunDir, $LogDir | Out-Null
if ($Offline) {
    $env:LLM_PROVIDER = 'mock'
    $env:LLM_API_KEY = ''
    $env:LLM_BASE_URL = ''
    $env:LLM_MODEL = ''
    $env:HYBRID_DENSE_ENABLED = 'false'
    $env:HYBRID_DENSE_WEIGHT = '0'
}
$env:PORT = [string]$BackendPort
$env:VITE_DEV_PORT = [string]$FrontendPort
$env:VITE_API_BASE_URL = "http://127.0.0.1:$BackendPort"

$backend = Start-Process -FilePath 'python' `
    -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',$BackendPort.ToString() `
    -WorkingDirectory (Join-Path $Root 'backend') `
    -RedirectStandardOutput (Join-Path $LogDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $LogDir 'backend.err.log') `
    -WindowStyle Hidden -PassThru

try {
    $backendReady = $false
    $backendWait = [Diagnostics.Stopwatch]::StartNew()
    while ($backendWait.Elapsed.TotalSeconds -lt 30) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSec 3
            if ($health.status -in @('healthy', 'degraded')) { $backendReady = $true; break }
        } catch {}
    }
    if (-not $backendReady) { throw 'Backend did not become ready within 30 seconds.' }

    $viteScript = Join-Path $Root 'frontend\node_modules\vite\bin\vite.js'
    $frontend = Start-Process -FilePath 'node' `
        -ArgumentList ('"{0}"' -f $viteScript),'--host','127.0.0.1','--port',$FrontendPort.ToString() `
        -WorkingDirectory (Join-Path $Root 'frontend') `
        -RedirectStandardOutput (Join-Path $LogDir 'frontend.out.log') `
        -RedirectStandardError (Join-Path $LogDir 'frontend.err.log') `
        -WindowStyle Hidden -PassThru

    $frontendReady = $false
    $frontendWait = [Diagnostics.Stopwatch]::StartNew()
    while ($frontendWait.Elapsed.TotalSeconds -lt 20) {
        Start-Sleep -Milliseconds 500
        try {
            $response = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/" -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) { $frontendReady = $true; break }
        } catch {}
    }
    if (-not $frontendReady) { throw 'Frontend did not become ready within 20 seconds.' }

    $state = @{
        root = $Root
        created_at = (Get-Date).ToUniversalTime().ToString('o')
        backend = @{
            pid = $backend.Id
            start_time = $backend.StartTime.ToUniversalTime().ToString('o')
            command_pattern = "uvicorn.*--port $BackendPort"
            port = $BackendPort
        }
        frontend = @{
            pid = $frontend.Id
            start_time = $frontend.StartTime.ToUniversalTime().ToString('o')
            command_pattern = "vite.*--port $FrontendPort"
            port = $FrontendPort
        }
    }
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Write-Output "Project started. Backend: http://127.0.0.1:$BackendPort  Frontend: http://127.0.0.1:$FrontendPort"
    Write-Output "Backend health: $($health.status); auth=$($health.auth_mode); LLM=$($health.llm_enabled); runtime_db=$($health.runtime_storage_ready)"
} catch {
    if ($frontend -and -not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force }
    if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
    throw
}
