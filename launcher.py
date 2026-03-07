import subprocess
import time
import sys
from datetime import datetime

# --- LISTA DE BOTS ---
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    # {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas Discord"}, # <--- COMENTADO (Desligado)
]

processos = {}


def log(mensagem):
    """Função para imprimir mensagens com a data e hora certinhas"""
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"[{agora}] {mensagem}")


def iniciar_bot(bot_config):
    """Inicia um bot e retorna o processo"""
    log(f"👉 Iniciando {bot_config['nome']}...")
    return subprocess.Popen([sys.executable, bot_config["arquivo"]])


log("🚀 INICIANDO SISTEMA TUFFINE...")

# Inicia todos os bots da lista pela primeira vez
for bot in bots:
    processos[bot["nome"]] = {"processo": iniciar_bot(bot), "config": bot}

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
                    f"⚠️ ALERTA: {nome} caiu ou foi finalizado! Reiniciando imediatamente..."
                )
                processos[nome]["processo"] = iniciar_bot(bot_config)

except KeyboardInterrupt:
    # Quando você mandar parar (Ctrl+C no terminal ou desligar na Discloud)
    log("🛑 Comando de parada recebido. Desligando bots...")
    for nome, dados in processos.items():
        dados["processo"].terminate()
        dados[
            "processo"
        ].wait()  # Garante que o processo foi morto de verdade, evitando processos zumbis
        log(f"💤 {nome} desligado com sucesso.")

    log("👋 Sistema Tuffine encerrado com segurança.")