#!/bin/bash
# network.sh - Network Benchmark Script

set -e

PROVIDER=$1
if [ -z "$PROVIDER" ]; then
    echo "Usage: $0 <provider>"
    exit 1
fi

TIMESTAMP=$(date +%s)
RESULTS_DIR="$(dirname $0)/results"
mkdir -p "$RESULTS_DIR"
OUT_FILE="${RESULTS_DIR}/network_${PROVIDER}_${TIMESTAMP}.json"

echo "Starting network benchmark for $PROVIDER..."

measure_curl_latency() {
    local url=$1
    curl -o /dev/null -s -w '{"time_namelookup": %{time_namelookup}, "time_connect": %{time_connect}, "time_appconnect": %{time_appconnect}, "time_pretransfer": %{time_pretransfer}, "time_redirect": %{time_redirect}, "time_starttransfer": %{time_starttransfer}, "time_total": %{time_total}}' "$url" || echo "{}"
}

echo "Testing Discord latency..."
discord_lat=$(measure_curl_latency "https://gateway.discord.gg")

echo "Testing OpenRouter latency..."
openrouter_lat=$(measure_curl_latency "https://openrouter.ai")

echo "Testing Stripe latency..."
stripe_lat=$(measure_curl_latency "https://api.stripe.com")

echo "DNS Latency..."
dns_google=$(dig @8.8.8.8 google.com | grep "Query time" | awk '{print $4}')
dns_cloudflare=$(dig @1.1.1.1 google.com | grep "Query time" | awk '{print $4}')

echo "MTR Traces (10 packets)..."
mtr_discord=$(mtr -c 10 --report --json gateway.discord.gg || echo "{}")
mtr_openrouter=$(mtr -c 10 --report --json openrouter.ai || echo "{}")
mtr_stripe=$(mtr -c 10 --report --json api.stripe.com || echo "{}")

echo "Ping statistics..."
ping_stats() {
    ping -c 10 -q $1 | tail -n 1 | awk -F '/' '{print "{\"min\": "$4", \"avg\": "$5", \"max\": "$6", \"stddev\": "$7"}"}' || echo "{}"
}

ping_discord=$(ping_stats gateway.discord.gg)
ping_openrouter=$(ping_stats openrouter.ai)
ping_stripe=$(ping_stats api.stripe.com)
ping_loopback=$(ping_stats 127.0.0.1)

cat <<EOF > "$OUT_FILE"
{
    "provider": "$PROVIDER",
    "timestamp": $TIMESTAMP,
    "latency_curl": {
        "discord": $discord_lat,
        "openrouter": $openrouter_lat,
        "stripe": $stripe_lat
    },
    "dns_query_time_ms": {
        "8.8.8.8": "$dns_google",
        "1.1.1.1": "$dns_cloudflare"
    },
    "mtr_traces": {
        "discord": $mtr_discord,
        "openrouter": $mtr_openrouter,
        "stripe": $mtr_stripe
    },
    "ping_stats": {
        "discord": $ping_discord,
        "openrouter": $ping_openrouter,
        "stripe": $ping_stripe,
        "loopback": $ping_loopback
    }
}
EOF

echo "Done. Results in $OUT_FILE"
