[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StatePath = Join-Path $Root '.codex\run\project-processes.json'
if (-not (Test-Path $StatePath)) {
    Write-Output 'No managed project processes were recorded; nothing was stopped.'
    exit 0
}
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
foreach ($name in @('frontend','backend')) {
    $expected = $state.$name
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($expected.pid)" -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $actual = Get-Process -Id $expected.pid -ErrorAction Stop
    $startMatches = $actual.StartTime.ToUniversalTime().ToString('o') -eq $expected.start_time
    if (-not $startMatches -or $process.CommandLine -notmatch $expected.command_pattern) {
        throw "Refusing to stop $name PID $($expected.pid): ownership markers do not match."
    }
    Stop-Process -Id $expected.pid -Force
    Write-Output "Stopped $name PID $($expected.pid)."
}
Remove-Item -LiteralPath $StatePath -Force
Write-Output 'Managed project processes stopped.'
