#!/usr/bin/env bash
# Tiffany OS — Local Pre-Commit & Release Validation Gates (Phase 11: Local & CI Equivalence)
# Ensures local code passes all release gates before pushing to origin/main or cutting a release.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONUTF8=1

echo "========================================================================"
echo "🛡️  Tiffany OS — Pre-Commit & Release Validation Pipeline"
echo "========================================================================"

echo ""
echo "[Gate A] Static Analysis & Syntax Verification..."
python -m py_compile *.py infra/*.py
echo "✅ Gate A: Syntax valid across all core modules."

echo ""
echo "[Gate B] Lifecycle & Core Unit Tests..."
python -m pytest test_postgres_config.py test_phase10_lifecycle.py test_phase11_lifecycle.py \
  test_outbox_concurrency.py test_payments_phase3.py test_launcher_signals.py \
  test_deployment_rollback.py test_premium_isolation.py test_failure_classification.py -v --tb=short
python -m unittest test_smoke -v
echo "✅ Gate B: Lifecycle, payments, isolation, rollback, diagnostics, and smoke tests passed."

echo ""
echo "[Gate C] Dedicated Music/Voice Regression & Isolation Suite..."
python -m unittest test_music_regression -v
echo "✅ Gate C: Music/Voice regression and fault isolation passed."

echo ""
echo "========================================================================"
echo "🎉 ALL LOCAL RELEASE GATES PASSED — SAFE TO PUSH / DEPLOY TO MAIN"
echo "========================================================================"
