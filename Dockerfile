FROM python:3.11-slim

# Instala ffmpeg (necessário para áudio/voz no Discord), nodejs (runtime JS para resolver desafios yt-dlp), netcat/curl para healthchecks e ferramentas essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia os requisitos primeiro para otimizar cache de build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do bot
COPY . .

# Cria grupo e usuário não-root tiffanyuser (UID/GID 10001) para execução de segurança em produção
RUN groupadd -g 10001 tiffany && \
    useradd -u 10001 -g tiffany -s /bin/sh -m tiffanyuser && \
    chown -R tiffanyuser:tiffany /app

USER tiffanyuser

# Healthcheck interno da aplicação usando a probe infra.health (verifica DB, Redis e Lavalink)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -m infra.health

# Execução do bot via python unbuffered
CMD ["python", "-u", "launcher.py"]
