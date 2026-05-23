#!/bin/bash
# Script de deploy para a VPS — chamado pelo GitHub Actions ou manualmente.
# Uso: bash /opt/tiffany-bot/scripts/deploy.sh

set -e

cd /opt/tiffany-bot

echo "[deploy] Baixando atualizações..."
git fetch origin main

echo "[deploy] Aplicando arquivos atualizados..."
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py affiliate_config.py 2>/dev/null || true
git checkout origin/main -- scripts/deploy.sh scripts/tiffany-bot.service 2>/dev/null || true

echo "[deploy] Reiniciando serviço..."
systemctl restart tiffany-bot

echo "[deploy] Aguardando inicialização..."
sleep 3

if systemctl is-active --quiet tiffany-bot; then
    echo "[deploy] ✅ Bot reiniciado com sucesso!"
    echo "[deploy] Processos ativos:"
    pgrep -a python3
else
    echo "[deploy] ❌ Falha ao iniciar! Verificar logs:"
    echo "  journalctl -u tiffany-bot -n 30 --no-pager"
    exit 1
fi
