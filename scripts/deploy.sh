#!/bin/bash
# Script de deploy para a VPS — chamado pelo GitHub Actions ou manualmente.
# Uso: bash /opt/tiffany-bot/scripts/deploy.sh

set -e

cd /opt/tiffany-bot

echo "[deploy] Baixando atualizações..."
git fetch origin main

echo "[deploy] Aplicando arquivos atualizados..."
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py affiliate_config.py random_songs.py requirements.txt 2>/dev/null || true
git checkout origin/main -- scripts/deploy.sh scripts/tiffany-bot.service CLAUDE.md 2>/dev/null || true

echo "[deploy] Atualizando service do systemd..."
cp -f scripts/tiffany-bot.service /etc/systemd/system/tiffany-bot.service
systemctl daemon-reload

echo "[deploy] Instalando dependências novas..."
pip3 install -q -r requirements.txt 2>/dev/null || true

echo "[deploy] Parando serviço e processos órfãos..."
systemctl stop tiffany-bot 2>/dev/null || true
sleep 1
# SIGKILL para garantir que nenhum processo sobreviva
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
rm -f /tmp/tiffany_launcher.lock
sleep 2
# Verificar se realmente morreu
if pgrep -f "/opt/tiffany-bot/(launcher|notices|offers).py" > /dev/null 2>&1; then
    echo "[deploy] ⚠️ Processos ainda vivos, forçando kill..."
    pkill -9 -f "/opt/tiffany-bot/" 2>/dev/null || true
    sleep 2
fi

echo "[deploy] Iniciando serviço..."
systemctl start tiffany-bot

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
