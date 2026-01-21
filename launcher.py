import subprocess
import time
import sys

# Lista de bots para rodar
bots = [
    {"arquivo": "notices.py", "nome": "📰 Bot Notícias"},
    # {"arquivo": "offers.py", "nome": "🛒 Bot Ofertas Discord"}, # <--- COMENTADO (Desligado temporariamente)
]

processos = []

print("🚀 INICIANDO SISTEMA TUFFINE...")

for bot in bots:
    print(f"   👉 Iniciando {bot['nome']}...")
    # Usa sys.executable para garantir que usa o mesmo python do ambiente
    p = subprocess.Popen([sys.executable, bot['arquivo']])
    processos.append(p)

print("✅ Bots ativos!")

try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    print("🛑 Parando bots...")
    for p in processos:
        p.terminate()