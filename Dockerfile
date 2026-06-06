FROM python:3.12-slim

# FFmpeg still needed for voice-recv (STT/clip), not for music playback
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create dirs for logs and data
RUN mkdir -p logs data

CMD ["python", "-u", "launcher.py"]
