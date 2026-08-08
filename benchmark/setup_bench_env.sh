#!/bin/bash
# setup_bench_env.sh - Setup benchmarking environment for Hostinger vs Hetzner

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

PROVIDER=$1
if [ -z "$PROVIDER" ]; then
    echo "Usage: $0 <provider> (e.g., hostinger or hetzner)"
    exit 1
fi

echo "Setting up benchmarking environment for $PROVIDER..."
export DEBIAN_FRONTEND=noninteractive

# Prerequisites
apt-get update
apt-get install -y fio sysbench stress-ng iperf3 mtr curl jq bc python3-pip python3-venv postgresql-16 redis-server wget gnupg2 lsb-release vim git

# Python dependencies
python3 -m venv /opt/bench_venv
source /opt/bench_venv/bin/activate
pip install asyncpg redis aiohttp numpy

# Configure PostgreSQL 16
echo "Configuring PostgreSQL 16..."
cat <<EOF > /etc/postgresql/16/main/postgresql.conf
listen_addresses = '*'
max_connections = 200
shared_buffers = 1GB
effective_cache_size = 3GB
maintenance_work_mem = 256MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 5MB
min_wal_size = 1GB
max_wal_size = 4GB
EOF

systemctl restart postgresql
systemctl enable postgresql

# Create schema
sudo -u postgres psql -c "CREATE USER tiffany WITH PASSWORD 'benchpass';" || true
sudo -u postgres psql -c "CREATE DATABASE tiffany OWNER tiffany;" || true

SCHEMA_DIR="$(cd "$(dirname "$0")/.." && pwd)/schema"
if [ -d "$SCHEMA_DIR" ]; then
    echo "Applying Tiffany schema migrations from $SCHEMA_DIR..."
    for sql_file in $(ls "$SCHEMA_DIR"/*.sql 2>/dev/null | sort); do
        echo "  Applying: $(basename $sql_file)"
        sudo -u postgres psql -d tiffany -f "$sql_file" || echo "  Warning: $(basename $sql_file) failed, continuing..."
    done
else
    echo "Schema directory not found at $SCHEMA_DIR, skipping schema creation."
fi

# Configure Redis 7
echo "Configuring Redis 7..."
cat <<EOF > /etc/redis/redis.conf
bind 127.0.0.1
port 6379
maxmemory 1gb
maxmemory-policy allkeys-lru
appendonly yes
EOF
systemctl restart redis-server
systemctl enable redis-server

# Validation
echo "Validating installation..."
command -v fio >/dev/null || { echo "fio missing"; exit 1; }
command -v sysbench >/dev/null || { echo "sysbench missing"; exit 1; }
command -v stress-ng >/dev/null || { echo "stress-ng missing"; exit 1; }
command -v iperf3 >/dev/null || { echo "iperf3 missing"; exit 1; }
command -v mtr >/dev/null || { echo "mtr missing"; exit 1; }
command -v jq >/dev/null || { echo "jq missing"; exit 1; }

mkdir -p benchmark/results

echo "Environment setup complete."
