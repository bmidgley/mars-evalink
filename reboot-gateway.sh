#!/usr/bin/env bash
set -e
PATH="$HOME/bin:$PATH"
exec >>/tmp/reboot-gateway.log 2>&1
date
meshtastic --reboot
