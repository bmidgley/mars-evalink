#!/usr/bin/env bash
set -e
PATH="$HOME/.local/bin:$PATH"
exec >>/tmp/reboot-gateway.log 2>&1
date
meshtastic --reboot