#!/bin/sh
# pgAdmin requires PGADMIN_DEFAULT_PASSWORD. On ZimaOS/CasaOS, env_file may not
# load or PGADMIN_DEFAULT_PASSWORD may be omitted; fall back to POSTGRES_PASSWORD.
set -eu

export PGADMIN_DEFAULT_EMAIL="${PGADMIN_DEFAULT_EMAIL:-admin@evalink.local}"
export PGADMIN_DEFAULT_PASSWORD="${PGADMIN_DEFAULT_PASSWORD:-${POSTGRES_PASSWORD:-}}"

if [ -z "$PGADMIN_DEFAULT_PASSWORD" ]; then
    echo "pgadmin entrypoint: set PGADMIN_DEFAULT_PASSWORD or POSTGRES_PASSWORD" >&2
    exit 1
fi

exec /entrypoint.sh "$@"
