#!/bin/bash
# Post-deploy health validation for GitHub Actions release workflow.
# Usage: EXPECTED_SHA=<full-sha> bash scripts/post-deploy-health.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/tiffany-bot}"
SERVICE_NAME="${SERVICE_NAME:-tiffany-bot}"
READINESS_TIMEOUT_SEC="${READINESS_TIMEOUT_SEC:-60}"
READINESS_INTERVAL_SEC="${READINESS_INTERVAL_SEC:-2}"

_count_repo_launchers() {
    local n=0 pid cwd
    for pid in $(pgrep -f "[l]auncher.py" 2>/dev/null || true); do
        cwd=$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || echo "")
        if [ "$cwd" = "$REPO_DIR" ]; then
            n=$((n + 1))
        fi
    done
    echo "$n"
}

_fail() {
    local reason="$1"
    echo "[HEALTH] HEALTH CHECK FAILURE"
    echo "[HEALTH] FAILURE REASON: ${reason}"
    echo "[HEALTH] EXPECTED SHA: ${EXPECTED_SHA:-<unset>}"
    echo "[HEALTH] CURRENT SHA: $(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "[HEALTH] SYSTEMD STATE: $(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo unknown)"
    echo "[HEALTH] ActiveState: $(systemctl show -p ActiveState --value "$SERVICE_NAME" 2>/dev/null || echo unknown)"
    echo "[HEALTH] SubState: $(systemctl show -p SubState --value "$SERVICE_NAME" 2>/dev/null || echo unknown)"
    echo "[HEALTH] MainPID: $(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || echo unknown)"
    echo "[HEALTH] Launcher count (${REPO_DIR}): $(_count_repo_launchers)"
    echo "[HEALTH] Recent journal (last 30 lines):"
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager 2>/dev/null || true
    exit 1
}

_wait_for_service_active() {
    local elapsed=0 state
    while [ "$elapsed" -lt "$READINESS_TIMEOUT_SEC" ]; do
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            state=$(systemctl show -p ActiveState --value "$SERVICE_NAME" 2>/dev/null || echo "")
            if [ "$state" = "active" ]; then
                return 0
            fi
        fi
        sleep "$READINESS_INTERVAL_SEC"
        elapsed=$((elapsed + READINESS_INTERVAL_SEC))
    done
    return 1
}

_verify_mainpid_launcher() {
    local main_pid cwd cmdline
    main_pid=$(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || echo "0")
    if [ -z "$main_pid" ] || [ "$main_pid" = "0" ]; then
        _fail "NO_LAUNCHER_FOUND"
    fi
    if ! kill -0 "$main_pid" 2>/dev/null; then
        _fail "NO_LAUNCHER_FOUND"
    fi
    cwd=$(readlink -f "/proc/${main_pid}/cwd" 2>/dev/null || echo "")
    if [ "$cwd" != "$REPO_DIR" ]; then
        _fail "NO_LAUNCHER_FOUND"
    fi
    cmdline=$(tr '\0' ' ' < "/proc/${main_pid}/cmdline" 2>/dev/null || echo "")
    if ! echo "$cmdline" | grep -q "launcher.py"; then
        _fail "NO_LAUNCHER_FOUND"
    fi
}

cd "$REPO_DIR" || _fail "REPO_DIR_MISSING"

echo "[HEALTH] Checking Docker status..."
docker compose ps || true

if [ -f docker-compose.yml ] && docker compose ps 2>/dev/null | grep -E "tiffany.*Up" >/dev/null; then
    echo "[HEALTH] Docker Compose mode detected and containers are running."
    echo "[HEALTH] Post-deploy health: OK"
    exit 0
fi

echo "[HEALTH] Fallback to systemd validation (Docker containers not detected as running)"

RUNNING_SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "[HEALTH] CURRENT SHA: ${RUNNING_SHA}"

if [ -n "${EXPECTED_SHA:-}" ] && [ "$RUNNING_SHA" != "$EXPECTED_SHA" ]; then
    _fail "EXPECTED_SHA_MISMATCH"
fi

if ! _wait_for_service_active; then
    _fail "STARTUP_TIMEOUT"
fi

ACTIVE_STATE=$(systemctl show -p ActiveState --value "$SERVICE_NAME" 2>/dev/null || echo "")
if [ "$ACTIVE_STATE" != "active" ]; then
    _fail "UNKNOWN_SYSTEMD_STATE"
fi

_verify_mainpid_launcher

LAUNCHERS="$(_count_repo_launchers)"
echo "[HEALTH] Launcher count (${REPO_DIR}): ${LAUNCHERS}"
if [ "$LAUNCHERS" -eq 0 ]; then
    _fail "NO_LAUNCHER_FOUND"
fi
if [ "$LAUNCHERS" -gt 1 ]; then
    _fail "MULTIPLE_LAUNCHERS"
fi

echo "[HEALTH] Post-deploy health: OK"
