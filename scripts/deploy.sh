#!/bin/bash
# Script de deploy para a VPS — chamado pelo GitHub Actions ou manualmente.
# Uso: bash /opt/tiffany-bot/scripts/deploy.sh

set -e

cd /opt/tiffany-bot

echo "[deploy] Baixando atualizações..."
git fetch origin main

echo "[deploy] Aplicando arquivos atualizados..."
git checkout origin/main -- launcher.py notices.py tiffany_voice.py offers.py offers_cog.py affiliate_config.py random_songs.py requirements.txt 2>/dev/null || true
git checkout origin/main -- scripts/deploy.sh scripts/tiffany-bot.service CLAUDE.md 2>/dev/null || true

echo "[deploy] Atualizando service do systemd..."
cp -f scripts/tiffany-bot.service /etc/systemd/system/tiffany-bot.service
systemctl daemon-reload

echo "[deploy] Instalando dependências novas..."
# NÃO esconder erro de pip: dependência quebrada = deploy silenciosamente quebrado.
pip3 install -q -r requirements.txt

# --- Deploy gracioso: espera música terminar antes de reiniciar ---
VOICE_STATE="/opt/tiffany-bot/voice_state.json"
MAX_WAIT=120  # máximo 2 minutos de espera
WAITED=0

if [ -f "$VOICE_STATE" ] && python3 -c "
import json, sys
with open('$VOICE_STATE') as f:
    data = json.load(f)
# Checa se algum servidor tem música tocando (current_query não vazio)
for gid, state in data.items():
    if state.get('current_query'):
        sys.exit(0)  # tem música tocando
sys.exit(1)  # ninguém tocando
" 2>/dev/null; then
    echo "[deploy] Música tocando — esperando fila esvaziar (máx ${MAX_WAIT}s)..."
    # Enviar SIGUSR1 para o bot sinalizar que deve parar após fila esvaziar
    # (por enquanto, apenas esperamos a música atual terminar via polling)
    while [ $WAITED -lt $MAX_WAIT ]; do
        sleep 5
        WAITED=$((WAITED + 5))
        # Re-checar se ainda tem música
        if ! python3 -c "
import json, sys
with open('$VOICE_STATE') as f:
    data = json.load(f)
for gid, state in data.items():
    if state.get('current_query'):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
            echo "[deploy] Fila esvaziou após ${WAITED}s — prosseguindo com restart."
            break
        fi
        echo "[deploy] Ainda tocando... (${WAITED}/${MAX_WAIT}s)"
    done
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "[deploy] Timeout de ${MAX_WAIT}s — reiniciando mesmo assim (fila será restaurada)."
    fi
else
    echo "[deploy] Nenhuma musica tocando — reiniciando imediatamente."
fi

echo "[deploy] Parando serviço e processos órfãos..."
systemctl stop tiffany-bot 2>/dev/null || true
sleep 2
# SIGKILL para garantir que nenhum processo sobreviva
pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
rm -f /tmp/tiffany_launcher.lock
sleep 3
# Verificar se realmente morreu — loop até confirmar.
# IMPORTANTE: NUNCA usar pkill -f "/opt/tiffany-bot/" genérico aqui — o próprio
# deploy.sh roda como "bash /opt/tiffany-bot/scripts/deploy.sh" e seria morto,
# derrubando a sessão SSH (exit 137) e causando falhas intermitentes no Actions.
# Por isso só matamos os scripts específicos do bot.
KILL_ATTEMPTS=0
while pgrep -f "/opt/tiffany-bot/(launcher|notices|offers).py" > /dev/null 2>&1; do
    KILL_ATTEMPTS=$((KILL_ATTEMPTS + 1))
    if [ $KILL_ATTEMPTS -ge 5 ]; then
        echo "[deploy] ERRO: processos nao morreram apos 5 tentativas!"
        break
    fi
    echo "[deploy] Processos ainda vivos (tentativa $KILL_ATTEMPTS), forcando kill..."
    pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
    sleep 3
done

echo "[deploy] Iniciando serviço..."
systemctl start tiffany-bot

echo "[deploy] Aguardando estabilização (10s)..."
# Type=simple marca "ativo" assim que o processo nasce, mesmo que caia logo depois.
# Por isso checamos de novo após 10s para pegar crash-loop / falha de import.
sleep 10

if systemctl is-active --quiet tiffany-bot; then
    echo "[deploy] Bot reiniciado com sucesso e estável!"
    echo "[deploy] Processos ativos:"
    pgrep -a python3 || true
else
    echo "[deploy] Serviço não está ativo após 10s! Últimos logs:"
    journalctl -u tiffany-bot -n 40 --no-pager || true
    exit 1
fi
