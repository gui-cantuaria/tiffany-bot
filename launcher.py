import subprocess
import time
import sys
import os
import fcntl
import urllib.request
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- LOCKFILE: garante que só uma instância roda ---
_LOCKFILE = "/tmp/tiffany_launcher.lock"
_lock_fd = open(_LOCKFILE, "w")
try:
    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print(f"[LOCK] Outra instância do launcher já está rodando. Encerrando duplicata.")
    sys.exit(0)

# --- LISTA DE BOTS ---
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    # {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas"},  # Pausado até configurar afiliados
]

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

processos = {}
_restart_times = {}  # nome -> lista de timestamps de restarts recentes
MAX_RESTARTS_RAPIDOS = 3  # máximo de restarts em janela
RESTART_JANELA = 60  # janela em segundos
RESTART_COOLDOWN = 300  # cooldown após restart storm (5 min)


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


def iniciar_bot(bot_config):
    """Inicia um bot e retorna o processo, capturando stdout/stderr em arquivo de log"""
    log(f"👉 Iniciando {bot_config['nome']}...")
    nome_base = os.path.splitext(bot_config["arquivo"])[0]
    log_path = os.path.join(LOG_DIR, f"{nome_base}.log")
    log_file = open(log_path, "a", encoding="utf-8")
    log_file.write(f"\n--- Iniciado em {datetime.now().isoformat()} ---\n")
    log_file.flush()
    proc = subprocess.Popen(
        [sys.executable, "-u", bot_config["arquivo"]],
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
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

        for nome, dados in processos.items():
            p = dados["processo"]
            bot_config = dados["config"]

            # Se o poll() retornar algo diferente de None, significa que o bot MORREU/FECHOU
            if p.poll() is not None:
                log(
                    f"⚠️ ALERTA: {nome} caiu (exit code: {p.returncode})!"
                )
                webhook_notify(f"⚠️ {nome} caiu (exit code: {p.returncode})!")
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
                proc, log_file = iniciar_bot(bot_config)
                processos[nome]["processo"] = proc
                processos[nome]["log_file"] = log_file

except KeyboardInterrupt:
    # Quando você mandar parar (Ctrl+C no terminal ou desligar na Discloud)
    log("🛑 Comando de parada recebido. Desligando bots...")
    webhook_notify("🛑 Sistema encerrado manualmente.")
    for nome, dados in processos.items():
        dados["processo"].terminate()
        dados["processo"].wait()
        if dados.get("log_file"):
            dados["log_file"].close()
        log(f"💤 {nome} desligado com sucesso.")

    log("👋 Sistema Tuffine encerrado com segurança.")