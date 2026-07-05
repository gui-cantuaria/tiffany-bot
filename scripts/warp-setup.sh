#!/bin/bash
# Install and configure Cloudflare WARP as a SOCKS5 proxy on 127.0.0.1:40000.
# yt-dlp uses this proxy to bypass YouTube's datacenter-IP blocks on the VPS.
#
# SAFETY: WARP is forced into "proxy" mode BEFORE connecting, so it never
# hijacks all traffic (which would drop the SSH session on a headless VPS).
#
# Idempotent: safe to run multiple times. Usage: bash scripts/warp-setup.sh

set -e

WARP_PORT="${WARP_PORT:-40000}"
KEYRING="/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg"
SRC_LIST="/etc/apt/sources.list.d/cloudflare-client.list"

echo "[warp] Ensuring Cloudflare WARP is installed..."
if ! command -v warp-cli &>/dev/null; then
    apt-get install -y lsb-release curl gpg
    curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor -o "$KEYRING"
    echo "deb [signed-by=$KEYRING] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" > "$SRC_LIST"
    apt-get update
    apt-get install -y cloudflare-warp
else
    echo "[warp] warp-cli already installed."
fi

echo "[warp] Starting warp-svc..."
systemctl enable warp-svc
systemctl start warp-svc
sleep 2

# Register only if not already registered (avoids error on re-run).
if ! warp-cli --accept-tos registration show &>/dev/null; then
    echo "[warp] Registering new WARP identity..."
    warp-cli --accept-tos registration new
else
    echo "[warp] Already registered."
fi

# CRITICAL: proxy mode BEFORE connect, so SSH is never tunneled.
echo "[warp] Setting proxy mode on port ${WARP_PORT}..."
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port "$WARP_PORT"
warp-cli --accept-tos connect
sleep 3

echo "[warp] Verifying proxy..."
if curl -s -x "socks5h://127.0.0.1:${WARP_PORT}" https://cloudflare.com/cdn-cgi/trace | grep -q "warp=on"; then
    echo "[warp] OK — proxy active (warp=on) on 127.0.0.1:${WARP_PORT}."
else
    echo "[warp] WARNING — proxy did not report warp=on. Check 'warp-cli status'."
    exit 1
fi
