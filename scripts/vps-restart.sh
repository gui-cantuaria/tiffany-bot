#!/bin/bash
# Reinicia o Tiffany Bot na VPS (mata só processos com cwd em /opt/tiffany-bot).
# Uso: bash scripts/vps-restart.sh
set -e
TIFFANY_DIR="/opt/tiffany-bot"
cd "$TIFFANY_DIR"

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

_count_by_cwd() {
  local pattern="$1"
  local n=0 pid cwd
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
    if [ "$cwd" = "$TIFFANY_DIR" ]; then
      n=$((n + 1))
    fi
  done
  echo "$n"
}

echo "==> Atualizando arquivos do GitHub..."
git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py scripts/vps-restart.sh affiliate_config.py offers.py 2>/dev/null || \
  git checkout origin/main -- launcher.py notices.py tiffany_voice.py scripts/vps-restart.sh

echo "==> Parando instâncias antigas (cwd $TIFFANY_DIR)..."
_kill_by_cwd "launcher.py"
_kill_by_cwd "notices.py"
_kill_by_cwd "offers.py"
sleep 2
rm -f /tmp/tiffany_launcher.lock

REMAIN=$(_count_by_cwd "launcher.py")
if [ "$REMAIN" -gt 0 ]; then
  echo "AVISO: ainda há $REMAIN launcher(s) — segunda passagem..."
  _kill_by_cwd "launcher.py"
  _kill_by_cwd "notices.py"
  sleep 2
  rm -f /tmp/tiffany_launcher.lock
fi

echo '{}' > voice_state.json

echo "==> Aguardando 3s..."
sleep 3

echo "==> Iniciando launcher..."
export PYTHONUNBUFFERED=1
nohup python3 launcher.py >> bot.log 2>&1 &
LAUNCHER_PID=$!
sleep 3

# Matar launchers duplicados (deixar só o que acabamos de subir)
for pid in $(pgrep -f "launcher.py" 2>/dev/null || true); do
  cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
  if [ "$cwd" = "$TIFFANY_DIR" ] && [ "$pid" != "$LAUNCHER_PID" ]; then
    echo "Removendo launcher duplicado PID $pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
done

if ps -p "$LAUNCHER_PID" >/dev/null 2>&1; then
  N=$(_count_by_cwd "launcher.py")
  echo "OK — launcher rodando (PID $LAUNCHER_PID, total launchers: $N)"
  pgrep -af "launcher.py" 2>/dev/null | while read -r line; do
    pid=$(echo "$line" | awk '{print $1}')
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "?")
    [ "$cwd" = "$TIFFANY_DIR" ] && echo "  $line"
  done
  if [ "$N" -gt 1 ]; then
    echo "AVISO: ainda há mais de 1 launcher no diretório Tiffany!"
    exit 1
  fi
else
  echo "ERRO — launcher morreu. Últimas linhas do log:"
  tail -40 logs/notices.log 2>/dev/null || tail -40 bot.log 2>/dev/null || true
  exit 1
fi
