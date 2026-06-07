import subprocess
import time
import sys
import os
import signal
import urllib.request
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- LOCKFILE: garante que só uma instância roda ---
_lock_fd = None
if sys.platform != "win32":
    import fcntl
    _LOCKFILE = "/tmp/tiffany_launcher.lock"
    _lock_fd = open(_LOCKFILE, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        _lock_fd.close()
        _lock_fd = None
        print("[LOCK] Outra instância do launcher já está rodando. Encerrando duplicata.")
        sys.exit(0)

# --- SIGTERM: systemctl stop envia SIGTERM, tratar como Ctrl+C ---
def _sigterm_handler(signum, frame):
    raise KeyboardInterrupt


if sys.platform != "win32":
    signal.signal(signal.SIGTERM, _sigterm_handler)


# --- LISTA DE BOTS ---
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas"},  # Afiliados configurados: Amazon, ML, Terabyte/ShopInfo
]

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

processos = {}
_restart_times = {}  # nome -> lista de timestamps de restarts recentes
_total_restarts = {}  # nome -> total de restarts desde o início
MAX_RESTARTS_RAPIDOS = 3  # máximo de restarts em janela
RESTART_JANELA = 60  # janela em segundos
RESTART_COOLDOWN = 300  # cooldown após restart storm (5 min)
MAX_TOTAL_RESTARTS = 15  # circuit breaker: desiste após N restarts totais


def log(mensagem):
    """Função para imprimir mensagens com a data e hora certinhas"""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{agora}] {mensagem}")


def webhook_notify(message: str):
    """Envia notificação de healthcheck via webhook do Discord."""
    url = os.environ.get("DISCORD_WEBHOOK_HEALTHCHECK")
    if not url:
        return
    try:
        data = json.dumps({"content": f"🤖 **Tiffany Healthcheck**\n{message}"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB por arquivo de log


def _truncar_log_se_grande(log_path: str) -> None:
    """Trunca arquivo de log se exceder MAX_LOG_SIZE, mantendo as últimas linhas."""
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > MAX_LOG_SIZE:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(max(0, os.path.getsize(log_path) - MAX_LOG_SIZE // 2))
                f.readline()  # descarta linha parcial
                conteudo = f.read()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"--- Log truncado em {datetime.now().isoformat()} ---\n")
                f.write(conteudo)
    except Exception:
        pass


def iniciar_bot(bot_config):
    """Inicia um bot e retorna o processo, capturando stdout/stderr em arquivo de log"""
    log(f"👉 Iniciando {bot_config['nome']}...")
    nome_base = os.path.splitext(bot_config["arquivo"])[0]
    log_path = os.path.join(LOG_DIR, f"{nome_base}.log")
    _truncar_log_se_grande(log_path)
    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write(f"\n--- Iniciado em {datetime.now().isoformat()} ---\n")
    log_file.flush()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", bot_config["arquivo"]],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        log_file.close()
        raise RuntimeError(f"Falha ao iniciar {bot_config['nome']}: {e}") from e
    return proc, log_file


log("🚀 INICIANDO SISTEMA TUFFINE...")

# Inicia todos os bots da lista pela primeira vez
for bot in bots:
    proc, log_file = iniciar_bot(bot)
    processos[bot["nome"]] = {"processo": proc, "log_file": log_file, "config": bot}

log("✅ Bots ativos! Monitorando quedas (Watchdog ativado)...")
webhook_notify(f"✅ Sistema iniciado com {len(bots)} bot(s)")

try:
    while True:
        # Checa a saúde dos bots a cada 10 segundos
        time.sleep(10)

        for nome, dados in list(processos.items()):
            p = dados["processo"]
            bot_config = dados["config"]

            # Se o poll() retornar algo diferente de None, significa que o bot MORREU/FECHOU
            if p.poll() is not None:
                log(
                    f"⚠️ ALERTA: {nome} caiu (exit code: {p.returncode})!"
                )
                webhook_notify(f"⚠️ {nome} caiu (exit code: {p.returncode})!")
                # Circuit breaker: desistir se crashou demais no total
                _total_restarts[nome] = _total_restarts.get(nome, 0) + 1
                if _total_restarts[nome] >= MAX_TOTAL_RESTARTS:
                    log(f"💀 {nome} crashou {MAX_TOTAL_RESTARTS}x no total! Desistindo permanentemente.")
                    webhook_notify(f"💀 {nome} desativado — crashou {MAX_TOTAL_RESTARTS}x. Requer restart manual.")
                    continue
                # Anti restart-storm: verificar se está crashando em loop
                agora = time.time()
                if nome not in _restart_times:
                    _restart_times[nome] = []
                _restart_times[nome].append(agora)
                # Manter só restarts recentes (dentro da janela)
                _restart_times[nome] = [t for t in _restart_times[nome] if agora - t < RESTART_JANELA]
                if len(_restart_times[nome]) >= MAX_RESTARTS_RAPIDOS:
                    log(f"🚨 {nome} crashou {MAX_RESTARTS_RAPIDOS}x em {RESTART_JANELA}s! Aguardando {RESTART_COOLDOWN}s...")
                    webhook_notify(f"🚨 {nome} em restart storm! Cooldown de {RESTART_COOLDOWN//60} min.")
                    time.sleep(RESTART_COOLDOWN)
                    _restart_times[nome].clear()
                # Fechar log file antigo
                if dados.get("log_file"):
                    dados["log_file"].close()
                log(f"🔄 Reiniciando {nome}...")
                try:
                    proc, log_file = iniciar_bot(bot_config)
                    processos[nome]["processo"] = proc
                    processos[nome]["log_file"] = log_file
                except Exception as e:
                    log(f"💀 Falha ao reiniciar {nome}: {e}")
                    webhook_notify(f"💀 Falha ao reiniciar {nome}: {e}")

except KeyboardInterrupt:
    # Quando você mandar parar (Ctrl+C no terminal ou desligar na Discloud)
    log("🛑 Comando de parada recebido. Desligando bots...")
    webhook_notify("🛑 Sistema encerrado manualmente.")
    for nome, dados in processos.items():
        dados["processo"].terminate()
        try:
            dados["processo"].wait(timeout=15)
        except subprocess.TimeoutExpired:
            log(f"⚠️ {nome} não encerrou em 15s, forçando kill...")
            dados["processo"].kill()
            dados["processo"].wait(timeout=5)
        if dados.get("log_file"):
            dados["log_file"].close()
        log(f"💤 {nome} desligado com sucesso.")

    log("👋 Sistema Tuffine encerrado com segurança.")
finally:
    # Liberar lockfile para permitir nova instância
    if _lock_fd:
        try:
            if sys.platform != "win32":
                import fcntl
                fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass