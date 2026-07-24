#!/bin/bash
# Kill every Tiffany bot process under /opt/tiffany-bot (any python path).
# Usage:
#   bash kill-orphans.sh           — stop systemd + kill all (manual/deploy)
#   bash kill-orphans.sh --pre-start — kill only (systemd ExecStartPre; always exit 0)
set -e
TIFFANY_DIR="/opt/tiffany-bot"
PRE_START=0
[ "${1:-}" = "--pre-start" ] && PRE_START=1

_kill_by_cwd() {
  local pattern="$1"
  local pid cwd
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
    if [ "$cwd" = "$TIFFANY_DIR" ]; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

if [ "$PRE_START" -eq 0 ]; then
  echo "[kill-orphans] Stopping systemd..."
  systemctl stop tiffany-bot 2>/dev/null || true
  sleep 2
fi

for _ in 1 2 3; do
  _kill_by_cwd "launcher.py"
  _kill_by_cwd "notices.py"
  _kill_by_cwd "offers.py"
  pkill -9 -f '[l]auncher.py' 2>/dev/null || true
  pkill -9 -f '[n]otices.py' 2>/dev/null || true
  pkill -9 -f '[o]ffers.py' 2>/dev/null || true
  sleep 1
  remain=$(pgrep -f "launcher.py" 2>/dev/null | wc -l)
  [ "$remain" -eq 0 ] && break
done

rm -f /tmp/tiffany_launcher.lock

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
