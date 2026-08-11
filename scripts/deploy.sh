#!/bin/bash
# Script de deploy para a VPS — chamado pelo GitHub Actions ou manualmente.
# Uso: bash /opt/tiffany-bot/scripts/deploy.sh
# Redesigned for Phase 12, 13, 14, 18: Atomic state preservation, deployment locking, and automatic rollback on health failure.
set -e

_deploy_main() {
cd /opt/tiffany-bot
REPO_DIR="$(pwd)"
LOCK_FILE="${REPO_DIR}/.deploy.lock"
PREV_RELEASE_FILE="${REPO_DIR}/.prev_good_release"
LAST_GOOD_FILE="${REPO_DIR}/.last_good_release"

# --- Phase 14: Deployment Locking against concurrent executions ---
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID="$(cat "$LOCK_FILE" 2>/dev/null || echo 0)"
    if [ "$LOCK_PID" -gt 0 ] && kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "[deploy] ⚠️ ERROR: Another deploy is already in progress (PID $LOCK_PID). Aborting concurrently safely."
        exit 1
    else
        echo "[deploy] Removing stale deploy lock file (PID $LOCK_PID no longer active)."
        rm -f "$LOCK_FILE"
    fi
fi

echo "$$" > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT INT TERM HUP

# Production VPS uses systemd + venv (not Docker).
export DEPLOY_MODE="${DEPLOY_MODE:-systemd}"
CURRENT_SHA="$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "[deploy] Current running commit: $CURRENT_SHA"

# Record current state as previous good release before touching workspace
if [ "$CURRENT_SHA" != "unknown" ]; then
    echo "$CURRENT_SHA" > "$PREV_RELEASE_FILE"
    echo "[deploy] Saved current commit $CURRENT_SHA to .prev_good_release for automatic rollback."
fi

echo "[deploy] Baixando e aplicando atualizações (git fetch & reset --hard para sincronia atômica de estado)..."
git fetch origin main
git reset --hard origin/main

NEW_SHA="$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
echo "[deploy] Target release commit: $NEW_SHA"

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
VENV="/opt/tiffany-bot/.venv"
PYTHON="${VENV}/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi
MAX_WAIT=120
WAITED=0

if [ -f "$VOICE_STATE" ] && "$PYTHON" -c "
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
        if ! "$PYTHON" -c "
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
    echo "[deploy] Parando systemd e processos órfãos sob garantia de instância única..."
    if [ -x scripts/kill-orphans.sh ]; then
        bash scripts/kill-orphans.sh || true
    else
        systemctl stop tiffany-bot 2>/dev/null || true
        pkill -TERM -f '[l]auncher.py' 2>/dev/null || true
        pkill -TERM -f '[n]otices.py' 2>/dev/null || true
        pkill -TERM -f '[o]ffers.py' 2>/dev/null || true
        sleep 10
        pkill -9 -f '[l]auncher.py' 2>/dev/null || true
        pkill -9 -f '[n]otices.py' 2>/dev/null || true
        pkill -9 -f '[o]ffers.py' 2>/dev/null || true
        rm -f /tmp/tiffany_launcher.lock
    fi
}

_trigger_rollback() {
    echo "[deploy] ❌ DEPLOY OR HEALTH CHECK FAILED — TRIGGERING AUTOMATIC ATOMIC ROLLBACK..."
    if [ -x scripts/rollback.sh ]; then
        bash scripts/rollback.sh || echo "[deploy] Rollback script also failed!"
    elif [ -f "$PREV_RELEASE_FILE" ]; then
        git reset --hard "$(cat "$PREV_RELEASE_FILE")" || true
        systemctl restart tiffany-bot || true
    fi
}

if [ "$USE_DOCKER" -eq 1 ]; then
    echo "[deploy] Modo Docker Compose..."
    _stop_systemd

    echo "[deploy] Rebuild e restart do container..."
    docker compose build --quiet || { _trigger_rollback; exit 1; }
    docker compose up -d --force-recreate --remove-orphans || { 
        echo "[deploy] Erro no docker compose up. Logs dos containers:"
        docker compose logs --tail 50
        _trigger_rollback; 
        exit 1; 
    }

    echo "[deploy] Aguardando estabilização (10s)..."
    sleep 10

    if docker compose ps --status running 2>/dev/null | grep -q tiffany; then
        echo "[deploy] Container Docker ativo!"
        echo "$NEW_SHA" > "$LAST_GOOD_FILE"
        exit 0
    fi

    echo "[deploy] Container não está running! Logs:"
    docker compose logs --tail=40 tiffany-bot 2>/dev/null || docker compose logs --tail=40
    _trigger_rollback
    exit 1
fi

echo "[deploy] Modo systemd..."
cp -f scripts/tiffany-bot.service /etc/systemd/system/tiffany-bot.service
chmod +x scripts/*.sh 2>/dev/null || true
systemctl daemon-reload

if [ -f scripts/tiffany-warp-healthcheck.timer ]; then
    cp -f scripts/tiffany-warp-healthcheck.service /etc/systemd/system/
    cp -f scripts/tiffany-warp-healthcheck.timer /etc/systemd/system/
    systemctl enable --now tiffany-warp-healthcheck.timer 2>/dev/null || true
fi

if [ ! -x "$VENV/bin/python" ]; then
    echo "[deploy] Criando venv..."
    (python3.11 -m venv "$VENV" 2>/dev/null) || python3 -m venv "$VENV"
fi
PIP_PYTHON="$VENV/bin/python"

echo "[deploy] Instalando dependências novas..."
"$PIP_PYTHON" -m pip install -q --no-cache-dir --upgrade pip || { _trigger_rollback; exit 1; }
"$PIP_PYTHON" -m pip install -q --no-cache-dir -r requirements.txt || { _trigger_rollback; exit 1; }

if [ -f .env ] && grep -qE '^LAVALINK_ENABLED=1' .env; then
    echo "[deploy] LAVALINK_ENABLED=1 — starting Lavalink container..."
    chmod +x scripts/start-lavalink.sh 2>/dev/null || true
    bash scripts/start-lavalink.sh 2>/dev/null || echo "[deploy] Lavalink start failed — bot will use yt-dlp fallback"
fi

_stop_systemd
rm -f /tmp/tiffany_launcher.lock

echo "[deploy] Iniciando serviço systemd..."
systemctl start tiffany-bot || { _trigger_rollback; exit 1; }

echo "[deploy] Aguardando estabilização (10s)..."
sleep 10

_count_tiffany_launchers() {
    local n=0 pid cwd
    for pid in $(pgrep -f "launcher.py" 2>/dev/null || true); do
        cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "")
        if [ "$cwd" = "/opt/tiffany-bot" ]; then
            n=$((n + 1))
        fi
    done
    echo "$n"
}

if ! systemctl is-active --quiet tiffany-bot; then
    echo "[deploy] Serviço inativo após 1ª tentativa — limpando órfãos e reiniciando..."
    rm -f /tmp/tiffany_launcher.lock
    bash scripts/kill-orphans.sh || true
    sleep 2
    systemctl start tiffany-bot || true
    sleep 10
fi

if systemctl is-active --quiet tiffany-bot; then
    LAUNCHERS=$(_count_tiffany_launchers)
    echo "[deploy] Bot reiniciado — launchers ativos (tiffany-bot): $LAUNCHERS"
    pgrep -af "launcher.py|notices.py" 2>/dev/null || true
    if [ "$LAUNCHERS" -gt 1 ]; then
        echo "[deploy] ERRO CRÍTICO: mais de 1 launcher. Duplicidade detectada!"
        _trigger_rollback
        exit 1
    fi
    if [ "$LAUNCHERS" -eq 0 ]; then
        echo "[deploy] ERRO: systemd ativo mas nenhum launcher em /opt/tiffany-bot"
        journalctl -u tiffany-bot -n 40 --no-pager || true
        _trigger_rollback
        exit 1
    fi
    RUNNING_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
    echo "[deploy] Running commit: $RUNNING_SHA"
    if [ -n "${EXPECTED_SHA:-}" ] && [ "$RUNNING_SHA" != "$EXPECTED_SHA" ]; then
        echo "[deploy] ERRO: SHA mismatch — expected $EXPECTED_SHA got $RUNNING_SHA"
        _trigger_rollback
        exit 1
    fi
    echo "[deploy] ✅ Post-deploy health: service active, launcher running, single instance verified!"
    echo "$RUNNING_SHA" > "$LAST_GOOD_FILE"
else
    echo "[deploy] Serviço não está ativo após 10s! Últimos logs:"
    journalctl -u tiffany-bot -n 40 --no-pager || true
    _trigger_rollback
    exit 1
fi
}

_deploy_main "$@"
