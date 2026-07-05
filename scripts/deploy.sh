#!/bin/bash
# Script de deploy para a VPS — chamado pelo GitHub Actions ou manualmente.
# Uso: bash /opt/tiffany-bot/scripts/deploy.sh
# Retrigger deploy: 2026-06-28
#
# Modos:
#   Docker (padrão se docker compose + docker-compose.yml existirem)
#   systemd (fallback) — defina DEPLOY_MODE=systemd para forçar

set -e

cd /opt/tiffany-bot

# Production VPS uses systemd + venv (not Docker).
export DEPLOY_MODE="${DEPLOY_MODE:-systemd}"

echo "[deploy] Baixando atualizações..."
git fetch origin main

echo "[deploy] Aplicando arquivos atualizados..."
git checkout origin/main -- \
  launcher.py notices.py tiffany_voice.py offers.py offers_cog.py \
  affiliate_config.py random_songs.py requirements.txt \
  docker-compose.yml Dockerfile .env.example 2>/dev/null || true
git checkout origin/main -- scripts/deploy.sh scripts/run.sh scripts/tiffany-bot.service \
  scripts/warp-setup.sh scripts/warp-healthcheck.sh scripts/setup-github-actions.sh \
  scripts/tiffany-warp-healthcheck.service scripts/tiffany-warp-healthcheck.timer \
  CLAUDE.md docs/voice-technical.md docs/python-migration.md docs/deploy-automation.md 2>/dev/null || true

USE_DOCKER=0
if [ "${DEPLOY_MODE:-}" = "systemd" ]; then
    USE_DOCKER=0
elif [ "${DEPLOY_MODE:-}" = "docker" ]; then
    USE_DOCKER=1
elif [ -f docker-compose.yml ] && docker compose version &>/dev/null; then
    USE_DOCKER=1
fi

# --- Deploy gracioso: espera música terminar antes de reiniciar ---
VOICE_STATE="/opt/tiffany-bot/voice_state.json"
MAX_WAIT=120
WAITED=0

if [ -f "$VOICE_STATE" ] && python3 -c "
import json, sys
with open('$VOICE_STATE') as f:
    data = json.load(f)
for gid, state in data.items():
    if state.get('current_query'):
        sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
    echo "[deploy] Música tocando — esperando fila esvaziar (máx ${MAX_WAIT}s)..."
    while [ $WAITED -lt $MAX_WAIT ]; do
        sleep 5
        WAITED=$((WAITED + 5))
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

_stop_systemd() {
    echo "[deploy] Parando systemd e processos órfãos..."
    systemctl stop tiffany-bot 2>/dev/null || true
    sleep 2
    pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
    pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
    rm -f /tmp/tiffany_launcher.lock
    sleep 2
    KILL_ATTEMPTS=0
    while pgrep -f "/opt/tiffany-bot/(launcher|notices|offers).py" > /dev/null 2>&1; do
        KILL_ATTEMPTS=$((KILL_ATTEMPTS + 1))
        if [ $KILL_ATTEMPTS -ge 5 ]; then
            echo "[deploy] AVISO: processos systemd ainda vivos após 5 tentativas."
            break
        fi
        pkill -9 -f "/opt/tiffany-bot/launcher.py" 2>/dev/null || true
        pkill -9 -f "/opt/tiffany-bot/notices.py" 2>/dev/null || true
        pkill -9 -f "/opt/tiffany-bot/offers.py" 2>/dev/null || true
        sleep 3
    done
}

if [ "$USE_DOCKER" -eq 1 ]; then
    echo "[deploy] Modo Docker Compose..."
    _stop_systemd

    echo "[deploy] Rebuild e restart do container..."
    docker compose build --quiet
    docker compose up -d --force-recreate --remove-orphans

    echo "[deploy] Aguardando estabilização (10s)..."
    sleep 10

    if docker compose ps --status running 2>/dev/null | grep -q tiffany; then
        echo "[deploy] Container Docker ativo!"
        docker compose ps
        echo "[deploy] Últimas linhas de log:"
        docker compose logs --tail=20 tiffany-bot 2>/dev/null || docker compose logs --tail=20
        exit 0
    fi

    echo "[deploy] Container não está running! Logs:"
    docker compose logs --tail=40 tiffany-bot 2>/dev/null || docker compose logs --tail=40
    exit 1
fi

echo "[deploy] Modo systemd..."
cp -f scripts/tiffany-bot.service /etc/systemd/system/tiffany-bot.service
chmod +x scripts/run.sh scripts/warp-setup.sh scripts/warp-healthcheck.sh 2>/dev/null || true
systemctl daemon-reload

# Ensure WARP healthcheck timer is installed (idempotent).
if [ -f scripts/tiffany-warp-healthcheck.timer ]; then
    cp -f scripts/tiffany-warp-healthcheck.service /etc/systemd/system/
    cp -f scripts/tiffany-warp-healthcheck.timer /etc/systemd/system/
    systemctl enable --now tiffany-warp-healthcheck.timer 2>/dev/null || true
fi

# Prefer the project venv (Python 3.11+); create it if missing.
VENV="/opt/tiffany-bot/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo "[deploy] Criando venv..."
    (python3.11 -m venv "$VENV" 2>/dev/null) || python3 -m venv "$VENV"
fi
PIP="$VENV/bin/pip"

echo "[deploy] Instalando dependências novas..."
"$PIP" install -q --upgrade pip
"$PIP" install -q -r requirements.txt

_stop_systemd

echo "[deploy] Iniciando serviço systemd..."
systemctl start tiffany-bot

echo "[deploy] Aguardando estabilização (10s)..."
sleep 10

if systemctl is-active --quiet tiffany-bot; then
    echo "[deploy] Bot reiniciado com sucesso e estável!"
    pgrep -a python3 || true
else
    echo "[deploy] Serviço não está ativo após 10s! Últimos logs:"
    journalctl -u tiffany-bot -n 40 --no-pager || true
    exit 1
fi
