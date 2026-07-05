#!/bin/bash
# Download the Vosk Portuguese model used as an offline STT fallback for the
# voice ("Tiffany, ...") feature. Without it, only OpenRouter/Google STT work
# and the offline fallback silently returns nothing.
#
# Run on the VPS: bash /opt/tiffany-bot/scripts/setup-vosk.sh

set -e

DEST="/opt/tiffany-bot/vosk-model-small-pt-0.3"
URL="https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
TMP="/tmp/vosk-pt.zip"

if [ -d "$DEST" ]; then
    echo "[vosk] Model already present: $DEST"
    exit 0
fi

echo "[vosk] Installing unzip if needed..."
command -v unzip >/dev/null 2>&1 || apt-get install -y unzip

echo "[vosk] Downloading model..."
curl -fSL "$URL" -o "$TMP"

echo "[vosk] Extracting..."
cd /opt/tiffany-bot
unzip -q "$TMP"
rm -f "$TMP"

if [ -d "$DEST" ]; then
    echo "[vosk] OK — model ready at $DEST"
else
    echo "[vosk] ERROR — expected folder not found after extraction. Check the archive layout."
    exit 1
fi
