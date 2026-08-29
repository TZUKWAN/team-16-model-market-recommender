[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StatePath = Join-Path $Root '.codex\run\project-processes.json'
if (-not (Test-Path $StatePath)) {
    Write-Output 'Project state: stopped or unmanaged (no PID state file).'
    exit 1
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$allValid = $true
foreach ($name in @('backend','frontend')) {
    $expected = $state.$name
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($expected.pid)" -ErrorAction SilentlyContinue
    $listener = Get-NetTCPConnection -LocalPort $expected.port -State Listen -ErrorAction SilentlyContinue
    $startMatches = $false
    try {
        $actual = Get-Process -Id $expected.pid -ErrorAction Stop
        $startMatches = $actual.StartTime.ToUniversalTime().ToString('o') -eq $expected.start_time
    } catch {}
    $valid = $process -and $startMatches -and $process.CommandLine -match $expected.command_pattern -and $listener.OwningProcess -eq $expected.pid
    if (-not $valid) { $allValid = $false }
    Write-Output "$name PID=$($expected.pid) port=$($expected.port) managed=$valid"
}
if ($allValid) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$($state.backend.port)/api/v1/health" -TimeoutSec 5
        Write-Output "health=$($health.status) auth=$($health.auth_mode) contract_tested=$($health.model_market_contract_tested) real_connected=$($health.model_market_real_connected)"
    } catch {
        Write-Output "health=unreachable ($($_.Exception.GetType().Name))"
        $allValid = $false
    }
}
if (-not $allValid) { exit 2 }
