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
# NÃO esconder erro de pip: dependência quebrada = deploy silenciosamente quebrado.
pip3 install -q -r requirements.txt

echo "[deploy] Parando serviço e processos órfãos..."
systemctl stop tiffany-bot 2>/dev/null || true
sleep 1
# SIGKILL para garantir que nenhum processo sobreviva
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
rm -f /tmp/tiffany_launcher.lock
sleep 2
# Verificar se realmente morreu.
# IMPORTANTE: NUNCA usar pkill -f "/opt/tiffany-bot/" genérico aqui — o próprio
# deploy.sh roda como "bash /opt/tiffany-bot/scripts/deploy.sh" e seria morto,
# derrubando a sessão SSH (exit 137) e causando falhas intermitentes no Actions.
# Por isso só matamos os scripts específicos do bot.
if pgrep -f "/opt/tiffany-bot/(launcher|notices|offers).py" > /dev/null 2>&1; then
    echo "[deploy] ⚠️ Processos ainda vivos, forçando kill..."
    pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
    sleep 2
fi

echo "[deploy] Iniciando serviço..."
systemctl start tiffany-bot

echo "[deploy] Aguardando estabilização (10s)..."
# Type=simple marca "ativo" assim que o processo nasce, mesmo que caia logo depois.
# Por isso checamos de novo após 10s para pegar crash-loop / falha de import.
sleep 10

if systemctl is-active --quiet tiffany-bot; then
    echo "[deploy] ✅ Bot reiniciado com sucesso e estável!"
    echo "[deploy] Processos ativos:"
    pgrep -a python3 || true
else
    echo "[deploy] ❌ Serviço não está ativo após 10s! Últimos logs:"
    journalctl -u tiffany-bot -n 40 --no-pager || true
    exit 1
fi
