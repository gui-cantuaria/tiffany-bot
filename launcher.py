import subprocess
import time
import sys
import os
from datetime import datetime

# --- LISTA DE BOTS ---
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    # {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas Discord"}, # <--- COMENTADO (Desligado)
]

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

processos = {}


def log(mensagem):
    """Função para imprimir mensagens com a data e hora certinhas"""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{agora}] {mensagem}")


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
                    f"⚠️ ALERTA: {nome} caiu (exit code: {p.returncode})! Reiniciando imediatamente..."
                )
                # Fechar log file antigo
                if dados.get("log_file"):
                    dados["log_file"].close()
                proc, log_file = iniciar_bot(bot_config)
                processos[nome]["processo"] = proc
                processos[nome]["log_file"] = log_file

except KeyboardInterrupt:
    # Quando você mandar parar (Ctrl+C no terminal ou desligar na Discloud)
    log("🛑 Comando de parada recebido. Desligando bots...")
    for nome, dados in processos.items():
        dados["processo"].terminate()
        dados["processo"].wait()
        if dados.get("log_file"):
            dados["log_file"].close()
        log(f"💤 {nome} desligado com sucesso.")

    log("👋 Sistema Tuffine encerrado com segurança.")