#!/bin/sh
# Restore a backup made by backup-now.sh, then verify it. Run on the server from the repository root:
#
#   sh deploy/backup/restore.sh deploy/backups/20261124-0100
#
# This REPLACES the current database and uploads. It asks for confirmation, stops the app while
# restoring, and finishes with `manage.py verify_integrity` (counts, stock ledger, payments, files).
set -eu

BACKUP=${1:?Usage: restore.sh <backup folder, e.g. deploy/backups/20261124-0100>}
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"

[ -f "$BACKUP/database.dump" ] || { echo "No database.dump in $BACKUP" >&2; exit 1; }
[ -f "$BACKUP/private_media.tar.gz" ] || { echo "No private_media.tar.gz in $BACKUP" >&2; exit 1; }

echo "Checking file integrity..."
( cd "$BACKUP" && sha256sum -c SHA256SUMS )

printf "This will REPLACE all current data with the backup in %s. Type RESTORE to continue: " "$BACKUP"
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

echo "Stopping the app (the database keeps running)..."
$COMPOSE stop web backend backup

echo "Restoring the database..."
$COMPOSE exec -T db sh -c 'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
$COMPOSE exec -T db sh -c 'pg_restore --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$BACKUP/database.dump"

echo "Restoring uploads..."
$COMPOSE run --rm -T --no-deps --entrypoint sh -v "$(pwd)/$BACKUP:/restore:ro" -u 0 backend \
  -c 'find /data/private_media -mindepth 1 -delete && tar -C /data -xzf /restore/private_media.tar.gz && chown -R 10001:10001 /data/private_media'

echo "Starting the app..."
$COMPOSE up -d backend web backup

echo "Verifying the restored data..."
$COMPOSE exec -T backend python manage.py verify_integrity
echo "Restore finished. Sign in and spot-check today's sales, a customer statement and a receipt photo."
