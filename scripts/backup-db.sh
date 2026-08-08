#!/usr/bin/env bash
# Automated PostgreSQL Backup Script for Tiffany OS
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tiffany}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/tiffany_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "${BACKUP_DIR}"

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $1"
}

log "Starting PostgreSQL backup..."

if [ -z "${DATABASE_URL:-}" ]; then
  log "ERROR: DATABASE_URL variable is not set."
  exit 1
fi

pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"

log "Backup completed successfully: ${BACKUP_FILE}"

# Cleanup backups older than RETENTION_DAYS
find "${BACKUP_DIR}" -name "tiffany_db_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
log "Cleaned up backups older than ${RETENTION_DAYS} days."
