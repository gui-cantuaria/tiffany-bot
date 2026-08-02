#!/usr/bin/env bash
# Tiffany OS — Atomic Release Rollback (Phase 12 & 18)
# Restores the last known healthy git commit and service state without destroying working code.
# Usage: bash /opt/tiffany-bot/scripts/rollback.sh [target_sha]

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO_DIR="$(pwd)"
PREV_RELEASE_FILE="${REPO_DIR}/.prev_good_release"

echo "========================================================================"
echo "🛡️  Tiffany OS — Atomic Release Rollback Procedure"
echo "========================================================================"

TARGET_SHA="${1:-}"
if [ -z "$TARGET_SHA" ]; then
    if [ -f "$PREV_RELEASE_FILE" ]; then
        TARGET_SHA="$(cat "$PREV_RELEASE_FILE" | tr -d ' \n\r')"
        echo "[rollback] No target SHA provided; using .prev_good_release: $TARGET_SHA"
    else
        echo "[rollback] ERROR: No target SHA provided and .prev_good_release file not found!"
        exit 1
    fi
fi

CURRENT_SHA="$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "[rollback] Current running commit: $CURRENT_SHA"
echo "[rollback] Target rollback commit: $TARGET_SHA"

if [ "$CURRENT_SHA" = "$TARGET_SHA" ]; then
    echo "[rollback] Target SHA is identical to current SHA. Re-verifying service health..."
else
    echo "[rollback] Reverting workspace cleanly to target SHA ($TARGET_SHA)..."
    git reset --hard "$TARGET_SHA"
fi

echo "[rollback] Restarting tiffany-bot service under single-instance protection..."
if [ -d "/etc/systemd/system" ] && systemctl list-unit-files | grep -q tiffany-bot; then
    if [ -x scripts/kill-orphans.sh ]; then
        bash scripts/kill-orphans.sh || true
    fi
    systemctl restart tiffany-bot
    sleep 5
    if systemctl is-active --quiet tiffany-bot; then
        echo "[rollback] ✅ Service restarted successfully and active!"
    else
        echo "[rollback] ❌ Service failed to activate after rollback! Journal logs:"
        journalctl -u tiffany-bot -n 30 --no-pager || true
        exit 1
    fi
else
    echo "[rollback] Systemd service not present (local/container mode). Code reset complete."
fi

# Update last good release record to reflect successful rollback
echo "$TARGET_SHA" > "${REPO_DIR}/.last_good_release"
echo "========================================================================"
echo "🎉 ROLLBACK COMPLETE — TIFFANY BOT RESTORED TO HEALTHY COMMIT: $TARGET_SHA"
echo "========================================================================"
