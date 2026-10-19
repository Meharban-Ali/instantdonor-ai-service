#!/usr/bin/env bash
# ==============================================================================
# scripts/backup_neon.sh — Neon PostgreSQL Backup Helper
# Reads DATABASE_URL / DB_URL from environment; zero hardcoded secrets
# ==============================================================================
set -euo pipefail

TARGET_URL="${DATABASE_URL:-${DB_URL:-}}"

if [ -z "$TARGET_URL" ]; then
  echo "[-] ERROR: DATABASE_URL or DB_URL environment variable must be set."
  exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/neon_backup_${TIMESTAMP}.dump"

echo "[+] Backing up database to ${BACKUP_FILE}..."
pg_dump \
  --dbname="$TARGET_URL" \
  --format=c \
  --no-owner \
  --no-privileges \
  --file="$BACKUP_FILE"

echo "[+] Backup created: ${BACKUP_FILE}"
