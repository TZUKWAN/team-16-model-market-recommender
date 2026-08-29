[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BaseCompose = Join-Path $Root 'docker-compose.yml'
$DenseCompose = Join-Path $Root 'docker-compose.dense.yml'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Required command is unavailable: docker'
}

Write-Host '[Team 16] Stopping this project without deleting model artifacts or runtime data...'
& docker compose `
    -f $BaseCompose `
    -f $DenseCompose `
    down `
    --remove-orphans

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose stop failed with exit code $LASTEXITCODE."
}

Write-Host '[Team 16] Competition runtime stopped.'
