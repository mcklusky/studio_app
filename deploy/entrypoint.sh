#!/bin/sh
# Apply database migrations, keep roles in sync, then start the server.
set -e
python manage.py migrate --noinput
python manage.py sync_access
exec "$@"
