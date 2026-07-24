#!/bin/bash
# Reinicia o Tiffany Bot na VPS — SOMENTE via systemd (nunca nohup).
# Uso: bash /opt/tiffany-bot/scripts/vps-restart.sh
set -e
TIFFANY_DIR="/opt/tiffany-bot"
cd "$TIFFANY_DIR"

echo "==> Atualizando arquivos do GitHub..."
git fetch origin main
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers_cog.py locale_utils.py \
  scripts/vps-restart.sh scripts/kill-orphans.sh scripts/tiffany-bot.service scripts/run.sh 2>/dev/null || true

echo "==> Matando instâncias duplicadas..."
bash "$TIFFANY_DIR/scripts/kill-orphans.sh"

echo "==> Recarregando unit systemd..."
cp -f scripts/tiffany-bot.service /etc/systemd/system/tiffany-bot.service
systemctl daemon-reload

echo "==> Iniciando tiffany-bot (1 instância)..."
systemctl start tiffany-bot
sleep 5

if ! systemctl is-active --quiet tiffany-bot; then
  echo "ERRO — service inativo. Logs:"
  journalctl -u tiffany-bot -n 30 --no-pager
  exit 1
fi

N=$(pgrep -f "launcher.py" 2>/dev/null | wc -l)
echo "Launchers ativos: $N"
pgrep -af "launcher.py|notices.py" || true

if [ "$N" -ne 1 ]; then
  echo "ERRO — deveria haver exatamente 1 launcher. Rode: bash scripts/kill-orphans.sh && systemctl restart tiffany-bot"
  exit 1
fi

echo "OK — Tiffany rodando via systemd."
journalctl -u tiffany-bot -n 15 --no-pager
