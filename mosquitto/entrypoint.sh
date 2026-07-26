#!/bin/sh
# Mosquitto entrypoint: prepare data/log dirs for the unprivileged broker user.
set -eu

mkdir -p /mosquitto/data /mosquitto/log

# The official image runs mosquitto as uid 1883.
chown -R 1883:1883 /mosquitto/data /mosquitto/log 2>/dev/null || true

exec "$@"
