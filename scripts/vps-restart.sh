#!/bin/bash
# Reinicia o Tiffany Bot na VPS sem matar o processo que acabou de subir.
# Uso: bash scripts/vps-restart.sh
set -e
cd /opt/tiffany-bot

echo "==> Atualizando arquivos do GitHub..."
git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py affiliate_config.py offers.py 2>/dev/null || \
  git checkout origin/main -- launcher.py notices.py tiffany_voice.py

echo "==> Parando instâncias antigas (só Tiffany)..."
# Mata todos os launchers/notices (evita duplicata 2630336 + 2631295)
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
sleep 1
pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
sleep 1
rm -f /tmp/tiffany_launcher.lock
echo '{}' > voice_state.json

echo "==> Aguardando 3s..."
sleep 3

echo "==> Iniciando launcher..."
export PYTHONUNBUFFERED=1
nohup python3 launcher.py >> bot.log 2>&1 &
LAUNCHER_PID=$!
sleep 2

if ps -p "$LAUNCHER_PID" >/dev/null 2>&1; then
  echo "OK — launcher rodando (PID $LAUNCHER_PID)"
  pgrep -af "/opt/tiffany-bot" || true
else
  echo "ERRO — launcher morreu. Últimas linhas do log:"
  tail -30 bot.log 2>/dev/null || tail -30 logs/notices.log 2>/dev/null || true
  exit 1
fi
