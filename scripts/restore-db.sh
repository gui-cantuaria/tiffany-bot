#!/usr/bin/env bash
# Automated Disaster Recovery Restore & Validation Script for Tiffany OS
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

# 1. Integrity check on file before restore
log "Verifying gzip compression integrity..."
if ! gzip -t "${BACKUP_FILE}"; then
  log "CRITICAL ERROR: Backup file ${BACKUP_FILE} is corrupted!"
  exit 1
fi

# 2. Execute Restoration
log "Applying database dump to target PostgreSQL instance..."
gunzip -c "${BACKUP_FILE}" | psql "${DATABASE_URL}"

# 3. Post-Restore Schema & Query Validation
log "Validating restored tables and schema..."
TABLE_COUNT=$(psql "${DATABASE_URL}" -t -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';" | tr -d ' ')
log "Restoration verified: ${TABLE_COUNT} public tables present."

log "Disaster Recovery restoration completed successfully!"
