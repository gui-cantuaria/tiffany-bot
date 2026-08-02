# Phase XII — run real PostgreSQL + Redis integration tests locally.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Starting integration infrastructure..."
docker compose -f docker-compose.integration.yml up -d --wait
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:TIFFANY_INTEGRATION_TESTS = "1"
$env:INTEGRATION_DATABASE_URL = "postgresql://tiffany_test:tiffany_test@127.0.0.1:5433/tiffany_test?ssl=disable"
$env:INTEGRATION_REDIS_URL = "redis://127.0.0.1:6380/0"
$env:DATABASE_URL = $env:INTEGRATION_DATABASE_URL
$env:REDIS_URL = $env:INTEGRATION_REDIS_URL

Write-Host "Running integration tests..."
py -m pytest tests/integration -v --tb=short
$code = $LASTEXITCODE

Write-Host "Integration test exit code: $code"
exit $code
