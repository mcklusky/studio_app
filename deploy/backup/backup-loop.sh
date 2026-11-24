#!/bin/sh
# Runs forever in the backup container: one backup at start-up, then one a day at BACKUP_HOUR (local time).
set -u
HOUR=${BACKUP_HOUR:-1}

sh /scripts/backup-now.sh || echo "[backup] FAILED at start-up; check the database connection" >&2

while true; do
  now=$(date +%s)
  today_target=$(date -d "$(date +%Y-%m-%d) $(printf '%02d' "$HOUR"):00:00" +%s 2>/dev/null || echo 0)
  if [ "$today_target" -le "$now" ]; then
    today_target=$((today_target + 86400))
  fi
  sleep $((today_target - now))
  sh /scripts/backup-now.sh || echo "[backup] FAILED; the next attempt is tomorrow. Investigate today." >&2
done
