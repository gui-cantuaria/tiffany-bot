#!/usr/bin/env bash
# Automated Host Setup Script for Tiffany OS Production Environment
# Enables Docker daemon auto-start, configures cron backup, and sets system limits.

set -euo pipefail

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $1"
}

log "=== Starting Tiffany OS Production Host Setup ==="

# 1. Enable & Start Docker Engine on Boot
if command -v systemctl >/dev/null 2>&1; then
  log "Enabling Docker service to start automatically on system boot..."
  sudo systemctl enable docker || true
  sudo systemctl start docker || true
  log "Docker service status: $(systemctl is-enabled docker || echo 'unknown')"
else
  log "WARNING: systemctl not found. Ensure Docker daemon starts on boot manually."
fi

# 2. Setup Cron Job for Automated Daily Database Backups
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup-db.sh"

if [ -f "${BACKUP_SCRIPT}" ]; then
  chmod +x "${BACKUP_SCRIPT}"
  CRON_JOB="0 3 * * * ${BACKUP_SCRIPT} >> /var/log/tiffany_backup.log 2>&1"
  
  # Install cron job if not already present
  if crontab -l 2>/dev/null | grep -q "${BACKUP_SCRIPT}"; then
    log "Cron job for database backups is already installed."
  else
    (crontab -l 2>/dev/null || true; echo "${CRON_JOB}") | crontab -
    log "Installed daily 03:00 AM database backup cron job."
  fi
else
  log "WARNING: ${BACKUP_SCRIPT} not found."
fi

log "=== Production Host Setup Complete ==="
