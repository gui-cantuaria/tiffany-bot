#!/usr/bin/env bash
# Automated PostgreSQL Backup & Offsite Replication Script for Tiffany OS
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tiffany}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/tiffany_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Offsite Storage Box Settings
STORAGE_BOX_USER="${STORAGE_BOX_USER:-}"
STORAGE_BOX_HOST="${STORAGE_BOX_HOST:-}"
STORAGE_BOX_PATH="${STORAGE_BOX_PATH:-/backups/tiffany}"

mkdir -p "${BACKUP_DIR}"

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $1"
}

cleanup_temp() {
  if [ $? -ne 0 ]; then
    log "ERROR: Backup pipeline failed unexpectedly!"
  fi
}
trap cleanup_temp EXIT

log "Starting PostgreSQL backup..."

if [ -z "${DATABASE_URL:-}" ]; then
  log "ERROR: DATABASE_URL variable is not set."
  exit 1
fi

# 1. Generate Compressed Backup
pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"

# 2. Integrity Verification
if [ ! -s "${BACKUP_FILE}" ]; then
  log "CRITICAL ERROR: Generated backup file is empty!"
  rm -f "${BACKUP_FILE}"
  exit 1
fi

if ! gzip -t "${BACKUP_FILE}"; then
  log "CRITICAL ERROR: Gzip integrity check failed for ${BACKUP_FILE}!"
  rm -f "${BACKUP_FILE}"
  exit 1
fi

log "Local backup completed and verified (${BACKUP_FILE})"

# 3. Local Retention Cleanup
find "${BACKUP_DIR}" -name "tiffany_db_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
log "Cleaned up local backups older than ${RETENTION_DAYS} days."

# 4. Optional Offsite Upload to Hetzner Storage Box
if [ -n "${STORAGE_BOX_USER}" ] && [ -n "${STORAGE_BOX_HOST}" ]; then
  log "Replicating backup offsite to Hetzner Storage Box (${STORAGE_BOX_HOST})..."
  rsync -avz -e "ssh -o StrictHostKeyChecking=accept-new" "${BACKUP_FILE}" "${STORAGE_BOX_USER}@${STORAGE_BOX_HOST}:${STORAGE_BOX_PATH}/"
  log "Offsite backup replication complete."
else
  log "NOTICE: STORAGE_BOX_USER / STORAGE_BOX_HOST unset — skipping offsite rsync."
fi

log "Backup pipeline finished successfully."
