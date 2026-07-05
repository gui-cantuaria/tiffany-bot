#!/bin/bash
# Verify the WARP SOCKS5 proxy is reachable; reconnect if it dropped.
# Intended to run periodically via tiffany-warp-healthcheck.timer.
#
# If the proxy is down, music playback (yt-dlp) fails silently, so we
# proactively bounce WARP back into a healthy state.

WARP_PORT="${WARP_PORT:-40000}"
TRACE_URL="https://cloudflare.com/cdn-cgi/trace"

if curl -s --max-time 10 -x "socks5h://127.0.0.1:${WARP_PORT}" "$TRACE_URL" | grep -q "warp=on"; then
    exit 0
fi

echo "[warp-healthcheck] Proxy down — attempting reconnect..."
systemctl start warp-svc 2>/dev/null || true
warp-cli --accept-tos mode proxy 2>/dev/null || true
warp-cli --accept-tos proxy port "$WARP_PORT" 2>/dev/null || true
warp-cli --accept-tos connect 2>/dev/null || true
sleep 5

if curl -s --max-time 10 -x "socks5h://127.0.0.1:${WARP_PORT}" "$TRACE_URL" | grep -q "warp=on"; then
    echo "[warp-healthcheck] Reconnected successfully."
    exit 0
fi

echo "[warp-healthcheck] ERROR — WARP still down after reconnect attempt."
exit 1
