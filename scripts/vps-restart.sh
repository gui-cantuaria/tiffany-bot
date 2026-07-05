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
git checkout origin/main -- launcher.py notices.py tiffany_voice.py scripts/vps-restart.sh affiliate_config.py offers_cog.py 2>/dev/null || \
  git checkout origin/main -- launcher.py notices.py tiffany_voice.py scripts/vps-restart.sh

echo "==> Parando instâncias antigas (cwd $TIFFANY_DIR)..."
for _ in 1 2 3; do
  _kill_by_cwd "launcher.py"
  _kill_by_cwd "notices.py"
  _kill_by_cwd "offers.py"
  sleep 2
  REMAIN=$(_count_by_cwd "launcher.py")
  [ "$REMAIN" -eq 0 ] && break
  echo "    ainda há $REMAIN launcher(s), tentando de novo..."
done
rm -f /tmp/tiffany_launcher.lock
echo '{}' > voice_state.json

if [ "$(_count_by_cwd "launcher.py")" -gt 0 ]; then
  echo "ERRO — não consegui parar todos os launchers. Rode:"
  echo "  pgrep -af launcher.py"
  exit 1
fi

echo "==> Aguardando 3s..."
sleep 3

echo "==> Iniciando launcher..."
export PYTHONUNBUFFERED=1
nohup python3 launcher.py >> bot.log 2>&1 &
sleep 5

N=$(_count_by_cwd "launcher.py")
if [ "$N" -eq 1 ]; then
  PID=$(pgrep -f "launcher.py" | while read -r p; do
    cwd=$(readlink -f "/proc/$p/cwd" 2>/dev/null || echo "")
    [ "$cwd" = "$TIFFANY_DIR" ] && echo "$p" && break
  done)
  echo "OK — launcher rodando (PID ${PID:-?}, total: $N)"
  tail -3 logs/notices.log 2>/dev/null | grep -E "Online|ERROR|Traceback" || true
elif [ "$N" -eq 0 ]; then
  echo "ERRO — nenhum launcher rodando. Últimas linhas:"
  tail -25 logs/notices.log 2>/dev/null || tail -25 bot.log 2>/dev/null || true
  exit 1
else
  echo "ERRO — $N launchers ainda ativos (deveria ser 1):"
  pgrep -af "launcher.py" || true
  exit 1
fi
