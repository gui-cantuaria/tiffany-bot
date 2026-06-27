FROM python:3.11-slim

# Instala ffmpeg (necessário para bots de música/voz no Discord) e ferramentas básicas
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os requisitos primeiro (isso otimiza o cache do Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do bot
COPY . .

# Comando para iniciar o bot
CMD ["python", "-u", "launcher.py"]
