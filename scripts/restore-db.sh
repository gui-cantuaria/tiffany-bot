#!/usr/bin/env bash
# Automated Disaster Recovery Restore Script for Tiffany OS
set -euo pipefail

BACKUP_FILE="${1:-}"

if [ -z "${BACKUP_FILE}" ] || [ ! -f "${BACKUP_FILE}" ]; then
  echo "Usage: $0 <path-to-backup-file.sql.gz>"
  exit 1
fi

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $1"
}

log "Starting Disaster Recovery restoration from: ${BACKUP_FILE}..."

if [ -z "${DATABASE_URL:-}" ]; then
  log "ERROR: DATABASE_URL variable is not set."
  exit 1
fi

gunzip -c "${BACKUP_FILE}" | psql "${DATABASE_URL}"

log "Disaster Recovery restoration completed successfully!"
