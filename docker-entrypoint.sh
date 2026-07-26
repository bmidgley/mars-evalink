#!/bin/sh
set -e

# ZimaOS / no-build compose: install Python deps once per container filesystem.
# Do not store the bootstrap marker on /app (bind-mounted from the host): a
# recreated container would skip pip install while site-packages are empty.
bootstrap_marker="/var/lib/evalink/.runtime_bootstrap_done"
bootstrap_needed=1
if [ -f "$bootstrap_marker" ] && python -c "import django" >/dev/null 2>&1; then
    bootstrap_needed=0
fi

if [ "$bootstrap_needed" -eq 1 ]; then
    echo "docker-entrypoint: installing runtime packages..."
    mkdir -p /var/lib/evalink
    apt-get update
    apt-get install -y --no-install-recommends postgresql-client
    rm -rf /var/lib/apt/lists/*
    pip install --no-cache-dir -r /app/requirements.runtime.txt
    touch "$bootstrap_marker"
    echo "docker-entrypoint: runtime bootstrap complete"
fi

cd /app/evalink

# Wait for the database to accept connections before running anything that
# touches it. compose's healthcheck handles this in most cases, but the wait
# also covers standalone "docker run" usage.
if [ -n "${HOST:-}" ] && command -v pg_isready >/dev/null 2>&1; then
    tries="${DB_WAIT_TRIES:-60}"
    while [ "$tries" -gt 0 ]; do
        if pg_isready -h "$HOST" -p "${PORT:-5432}" -U "${DBUSER:-postgres}" -d "${NAME:-postgres}" >/dev/null 2>&1; then
            break
        fi
        tries=$((tries - 1))
        sleep 1
    done
    if [ "$tries" -eq 0 ]; then
        echo "docker-entrypoint: timed out waiting for postgres at $HOST:${PORT:-5432}" >&2
        exit 1
    fi
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

# Create the Django admin user on first boot when missing. Password comes from
# WEB_ADMIN_PASSWORD (default: evalink9). Existing users are left alone.
export WEB_ADMIN_PASSWORD="${WEB_ADMIN_PASSWORD:-evalink9}"
export WEB_ADMIN_USER="${WEB_ADMIN_USER:-admin}"
python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get("WEB_ADMIN_USER", "admin")
password = os.environ["WEB_ADMIN_PASSWORD"]
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, "", password)
    print(f"docker-entrypoint: created Django admin user {username!r}")
else:
    print(f"docker-entrypoint: Django admin user {username!r} already exists")
PY

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ] && [ -n "${STATIC_ROOT:-}" ]; then
  python manage.py collectstatic --noinput
fi

if [ "$1" = "gunicorn" ]; then
  shift
  exec gunicorn evalink.wsgi:application \
    --bind "0.0.0.0:${WEB_PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-1}" \
    "$@"
else
  exec "$@"
fi
