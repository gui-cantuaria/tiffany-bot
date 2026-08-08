#!/bin/bash
# hardware.sh - Hardware Benchmark Script

set -e

PROVIDER=$1
if [ -z "$PROVIDER" ]; then
    echo "Usage: $0 <provider>"
    exit 1
fi

TIMESTAMP=$(date +%s)
RESULTS_DIR="$(dirname $0)/results"
mkdir -p "$RESULTS_DIR"
OUT_FILE="${RESULTS_DIR}/hardware_${PROVIDER}_${TIMESTAMP}.json"

echo "Starting hardware benchmark for $PROVIDER..."
source /opt/bench_venv/bin/activate || true

cat << 'EOF' > /tmp/stats.py
import sys, json, numpy as np
try:
    data = [float(x.strip()) for x in sys.stdin.readlines() if x.strip()]
    if not data:
        print(json.dumps({"error": "no data"}))
        sys.exit(0)
    print(json.dumps({
        "P50": np.percentile(data, 50),
        "P95": np.percentile(data, 95),
        "P99": np.percentile(data, 99),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
        "stddev": float(np.std(data)),
        "mean": float(np.mean(data))
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))
EOF

run_sysbench_cpu() {
    local threads=$1
    local trials=$2
    rm -f /tmp/sysbench_cpu.txt
    for i in $(seq 1 $trials); do
        sysbench cpu --cpu-max-prime=20000 --threads=$threads --time=30 run | grep "events per second:" | awk '{print $4}' >> /tmp/sysbench_cpu.txt
    done
    cat /tmp/sysbench_cpu.txt | python3 /tmp/stats.py
}

echo "CPU Single-core..."
cpu_single=$(run_sysbench_cpu 1 10)

echo "CPU Multi-core..."
cores=$(nproc)
cpu_multi=$(run_sysbench_cpu $cores 10)

echo "stress-ng sustained (5m)..."
stress_output=$(stress-ng --cpu $cores --timeout 5m --metrics-brief 2>&1 | grep "cpu " | awk '{print $9}' || echo "0")

echo "vmstat steal time (5m)..."
vmstat_output=$(vmstat 1 300 | awk 'NR>2 {print $16}' | python3 /tmp/stats.py || echo "{}")

cpu_info=$(cat /proc/cpuinfo | grep "model name" | head -n 1 | cut -d ":" -f2 | sed 's/^ *//')

echo "Memory read/write..."
mem_read=$(sysbench memory --memory-oper=read --memory-access-mode=seq run | grep "MiB/sec" | grep -o -E '[0-9.]+')
mem_write=$(sysbench memory --memory-oper=write --memory-access-mode=seq run | grep "MiB/sec" | grep -o -E '[0-9.]+')

run_fio() {
    local rw=$1
    local bs=$2
    local size="1G"
    fio --name=test --ioengine=libaio --iodepth=64 --rw=$rw --bs=$bs --direct=1 --size=$size --numjobs=1 --runtime=30 --group_reporting --output-format=json | jq '.jobs[0]' || echo "{}"
}

echo "Disk testing..."
disk_read_4k=$(run_fio "read" "4k")
disk_write_4k=$(run_fio "write" "4k")
disk_randread_4k=$(run_fio "randread" "4k")
disk_randwrite_4k=$(run_fio "randwrite" "4k")
disk_randrw_4k=$(run_fio "randrw" "4k")

echo "fsync latency test..."
fsync_lat=$(sysbench fileio --file-test-mode=rndwr --file-total-size=1G prepare >/dev/null && sysbench fileio --file-test-mode=rndwr --file-total-size=1G --file-fsync-freq=1 run | grep "fsyncs/s" | grep -o -E '[0-9.]+' && sysbench fileio --file-total-size=1G cleanup >/dev/null || echo "0")

cat <<EOF > "$OUT_FILE"
{
    "provider": "$PROVIDER",
    "timestamp": $TIMESTAMP,
    "cpu": {
        "model": "$cpu_info",
        "cores": $cores,
        "sysbench_single": $cpu_single,
        "sysbench_multi": $cpu_multi,
        "stress_ng_bogo_ops": "$stress_output",
        "steal_time_stats": $vmstat_output
    },
    "memory": {
        "read_mib_s": "$mem_read",
        "write_mib_s": "$mem_write"
    },
    "disk": {
        "read_4k": $disk_read_4k,
        "write_4k": $disk_write_4k,
        "randread_4k": $disk_randread_4k,
        "randwrite_4k": $disk_randwrite_4k,
        "randrw_4k": $disk_randrw_4k,
        "fsync_lat_s": "$fsync_lat"
    }
}
EOF

echo "Done. Results in $OUT_FILE"
