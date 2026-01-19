import subprocess
import time
import sys

# Lista de bots para rodar
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas Discord"},
    # Se você já tiver o arquivo do telegram, descomente a linha abaixo:
    # {"arquivo": "telegram_offers.py", "nome": "✈️ Bot Ofertas Telegram"} 
]

processos = []

print("🚀 INICIANDO SISTEMA TUFFINE...")

for bot in bots:
    print(f"   👉 Iniciando {bot['nome']}...")
    # Cria o processo independente para cada bot
    p = subprocess.Popen([sys.executable, bot['arquivo']])
    processos.append(p)

print("✅ Todos os bots estão rodando!")

try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    print("🛑 Parando bots...")
    for p in processos:
        p.terminate()