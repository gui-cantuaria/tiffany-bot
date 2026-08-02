#!/bin/bash
# Kill every Tiffany bot process under /opt/tiffany-bot (any python path).
# Usage:
#   bash kill-orphans.sh           — stop systemd + kill all (manual/deploy)
#   bash kill-orphans.sh --pre-start — kill only (systemd ExecStartPre; always exit 0)
set -e
TIFFANY_DIR="/opt/tiffany-bot"
PRE_START=0
[ "${1:-}" = "--pre-start" ] && PRE_START=1

_graceful_kill_by_cwd() {
  local pattern="$1"
  local sig="$2"
  local pid cwd
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
    if [ "$cwd" = "$TIFFANY_DIR" ]; then
      kill -"$sig" "$pid" 2>/dev/null || true
    fi
  done
}

if [ "$PRE_START" -eq 0 ]; then
  echo "[kill-orphans] Stopping systemd..."
  systemctl stop tiffany-bot 2>/dev/null || true
  sleep 2
fi

# Phase 1: graceful SIGTERM (allows discord.py to close gateway cleanly)
echo "[kill-orphans] Sending SIGTERM (graceful)..."
_graceful_kill_by_cwd "launcher.py" TERM
_graceful_kill_by_cwd "notices.py" TERM
_graceful_kill_by_cwd "offers.py" TERM
pkill -TERM -f '[l]auncher.py' 2>/dev/null || true
pkill -TERM -f '[n]otices.py' 2>/dev/null || true
pkill -TERM -f '[o]ffers.py' 2>/dev/null || true

# Wait up to 10s for graceful shutdown
for i in $(seq 1 10); do
  remain=$(pgrep -f "launcher.py|notices.py" 2>/dev/null | wc -l)
  [ "$remain" -eq 0 ] && break
  sleep 1
done

# Phase 2: SIGKILL only if processes survived SIGTERM
remain=$(pgrep -f "launcher.py|notices.py" 2>/dev/null | wc -l)
if [ "$remain" -gt 0 ]; then
  echo "[kill-orphans] Processes survived SIGTERM — sending SIGKILL..."
  for _ in 1 2; do
    _graceful_kill_by_cwd "launcher.py" KILL
    _graceful_kill_by_cwd "notices.py" KILL
    _graceful_kill_by_cwd "offers.py" KILL
    pkill -9 -f '[l]auncher.py' 2>/dev/null || true
    pkill -9 -f '[n]otices.py' 2>/dev/null || true
    pkill -9 -f '[o]ffers.py' 2>/dev/null || true
    sleep 1
    remain=$(pgrep -f "launcher.py" 2>/dev/null | wc -l)
    [ "$remain" -eq 0 ] && break
  done
fi

if command -v docker &>/dev/null; then
  docker ps -q --filter "name=tiffany" | xargs -r docker stop 2>/dev/null || true
fi

rm -f /tmp/tiffany_*.lock

left=$(pgrep -af "launcher.py|notices.py" 2>/dev/null || true)
if [ -n "$left" ]; then
  echo "[kill-orphans] AVISO — processos restantes:" >&2
  echo "$left" >&2
  if [ "$PRE_START" -eq 0 ]; then
    exit 1
  fi
  exit 0
fi

echo "[kill-orphans] OK — nenhum launcher/notices ativo."
