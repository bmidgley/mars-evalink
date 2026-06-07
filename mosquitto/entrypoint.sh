#!/bin/sh
# Mosquitto entrypoint: bootstrap a password file from MQTT_USER / MQTT_PASSWORD,
# fix ownership for the unprivileged "mosquitto" user, then exec the broker.
set -eu

PASSWD_FILE="/mosquitto/data/passwd"

if [ -z "${MQTT_USER:-}" ] || [ -z "${MQTT_PASSWORD:-}" ]; then
    echo "mosquitto entrypoint: MQTT_USER and MQTT_PASSWORD must be set" >&2
    exit 1
fi

mkdir -p /mosquitto/data /mosquitto/log

# (Re)generate the password file every boot so credential changes in .env
# take effect on "docker compose up". This wipes any other accounts; if you
# need multiple users, manage the file out-of-band and remove this block.
: > "$PASSWD_FILE"
mosquitto_passwd -b "$PASSWD_FILE" "$MQTT_USER" "$MQTT_PASSWORD"
chmod 0600 "$PASSWD_FILE"

# The official image runs mosquitto as uid 1883.
chown -R 1883:1883 /mosquitto/data /mosquitto/log 2>/dev/null || true

exec "$@"
