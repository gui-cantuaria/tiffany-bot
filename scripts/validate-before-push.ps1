# Tiffany OS - Local Pre-Commit and Release Validation Gates (PowerShell Edition)
# Ensures local code passes all release gates before pushing to origin/main or cutting a release.
$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot\.."
$env:PYTHONUTF8 = "1"

Write-Host "========================================================================" -ForegroundColor Magenta
Write-Host "Tiffany OS - Pre-Commit and Release Validation Pipeline" -ForegroundColor Magenta
Write-Host "========================================================================" -ForegroundColor Magenta

Write-Host "`n[Gate A] Static Analysis and Syntax Verification..." -ForegroundColor Cyan
Get-ChildItem -Path . -Filter "*.py" -File | ForEach-Object { py -m py_compile $_.FullName }
Get-ChildItem -Path infra -Filter "*.py" -File | ForEach-Object { py -m py_compile $_.FullName }
Write-Host "[Gate A PASSED]: Syntax valid across all core modules." -ForegroundColor Green

Write-Host "`n[Gate B] Lifecycle and Core Unit Tests..." -ForegroundColor Cyan
py -m pytest test_postgres_config.py test_phase10_lifecycle.py test_phase11_lifecycle.py test_outbox_concurrency.py test_payments_phase3.py test_launcher_signals.py test_deployment_rollback.py test_premium_isolation.py test_failure_classification.py -v --tb=short
if ($LASTEXITCODE -ne 0) { throw "pytest failed!" }

py -m unittest test_smoke -v
if ($LASTEXITCODE -ne 0) { throw "test_smoke failed!" }
Write-Host "[Gate B PASSED]: Lifecycle, payments, isolation, rollback, diagnostics, and smoke tests passed." -ForegroundColor Green

Write-Host "`n[Gate C] Dedicated Music/Voice Regression and Isolation Suite..." -ForegroundColor Cyan
py -m unittest test_music_regression -v
if ($LASTEXITCODE -ne 0) { throw "test_music_regression failed!" }
Write-Host "[Gate C PASSED]: Music/Voice regression and fault isolation passed." -ForegroundColor Green

Write-Host "`n========================================================================" -ForegroundColor Magenta
Write-Host "ALL LOCAL RELEASE GATES PASSED - SAFE TO PUSH OR DEPLOY TO MAIN" -ForegroundColor Green
Write-Host "========================================================================" -ForegroundColor Magenta
