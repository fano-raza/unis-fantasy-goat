#!/usr/bin/env bash
set -euo pipefail

# Backup state/data snapshots to timestamped tarball.
DATA_DIR="${DATA_DIR:-/srv/unisfantasy/data}"
STATE_DIR="${STATE_DIR:-/srv/unisfantasy/state}"
BACKUP_DIR="${BACKUP_DIR:-/srv/unisfantasy/backups}"

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/unisfantasy_backup_${TS}.tar.gz"

echo "[backup] creating $OUT"

tar -czf "$OUT" \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  -C / "$DATA_DIR" "$STATE_DIR" 2>/dev/null || true

echo "[backup] complete: $OUT"
