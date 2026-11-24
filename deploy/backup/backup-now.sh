#!/bin/sh
# One backup: a compressed PostgreSQL dump plus an archive of the private uploads,
# each with a SHA-256 checksum. Runs inside the "backup" container (see docker-compose.prod.yml):
#   docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec backup sh /scripts/backup-now.sh
set -eu

STAMP=$(date +%Y%m%d-%H%M)
DIR=/backups/$STAMP
mkdir -p "$DIR"

echo "[backup] $STAMP: database"
pg_dump --format=custom --compress=6 --no-owner --file="$DIR/database.dump"
# A dump that cannot be listed is unusable; fail loudly instead of keeping it.
pg_restore --list "$DIR/database.dump" > /dev/null

echo "[backup] $STAMP: uploads"
tar -C /data -czf "$DIR/private_media.tar.gz" private_media

( cd "$DIR" && sha256sum database.dump private_media.tar.gz > SHA256SUMS )
echo "$STAMP" > /backups/LATEST

echo "[backup] removing backups older than ${RETENTION_DAYS:-30} days"
find /backups -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +"${RETENTION_DAYS:-30}" -exec rm -r -- {} +

SIZE=$(du -sh "$DIR" | cut -f1)
echo "[backup] done: $DIR ($SIZE)"
