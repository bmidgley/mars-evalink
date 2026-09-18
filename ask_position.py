#!/usr/bin/env python3
"""
Standalone script: fetch stalenode JSON from evalink and run
meshtastic --request-position --dest <hardware_node> for each stale station.

The gateway radio uplinks the remote node's position reply as JSON MQTT
({MQTT_TOPIC}/+/json/#, type=position). Django mqtt.py watches that topic
and updates the station — this script only triggers the request; it does
not republish.

Requires: meshtastic CLI, python-dotenv (optional, loads .env).
Env: MESHTASTIC_REQUEST_POSITION_TIMEOUT (seconds, default 180)

stalenode returns JSON: delay_minutes, mqtt_downlink_topic, gateway_node_number,
and stations[] with hardware_node, hardware_number, channel, etc.

sample meshtastic output:
$ meshtastic --request-position --dest \!1d392cde
Connected to radio
Sending position request to !1d392cde on channelIndex:0 (this could take a while)
Position received: (38.4063486, -110.7920051) 1377m full precision
$
"""
import json
import os
import re
import subprocess
import urllib.request

STALENODE_URL = "https://evalink.archresearch.net/stalenode?delay=1"

_POSITION_LINE = re.compile(
    r"Position received:\s*\(\s*([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*,\s*"
    r"([-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)\s*\)(?:\s+(\d+)m)?",
    re.IGNORECASE,
)

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_a, **_k):
        return False


def _print_no_stale():
    print("No stale nodes found")


def parse_meshtastic_position_output(text):
    """
    Extract lat, lon, and optional altitude (meters) from meshtastic stdout/stderr.
    Returns dict with keys latitude, longitude, altitude (altitude may be None) or None.
    Used only for CLI logging; persistence is via MQTT uplink from the gateway.
    """
    if not text or not text.strip():
        return None
    m = _POSITION_LINE.search(text)
    if not m:
        return None
    lat = float(m.group(1))
    lon = float(m.group(2))
    alt = int(m.group(3)) if m.group(3) else None
    return {"latitude": lat, "longitude": lon, "altitude": alt}


def main():
    load_dotenv()
    try:
        with urllib.request.urlopen(STALENODE_URL) as resp:
            body = resp.read().decode("utf-8").strip()
    except Exception as e:
        print(f"Failed to fetch stalenode: {e}")
        return 1
    if not body:
        _print_no_stale()
        return 0
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from stalenode: {e}")
        return 1
    stations = data.get("stations") or []
    if not stations:
        _print_no_stale()
        return 0
    try:
        timeout = int(os.getenv("MESHTASTIC_REQUEST_POSITION_TIMEOUT", "180"))
    except ValueError:
        timeout = 180
    for station in stations:
        node = (station.get("hardware_node") or "").strip()
        if not node:
            continue
        hw_num = station.get("hardware_number")
        if hw_num is None:
            print(f"skip {node}: missing hardware_number in stalenode payload")
            continue
        cmd = ["meshtastic", "--request-position", "--dest", node]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            print("meshtastic not found; skipped remaining stations")
            return 1
        except subprocess.TimeoutExpired:
            print(f"meshtastic timed out after {timeout}s for {node}")
            continue
        except Exception as e:
            print(f"Error running meshtastic --dest {node}: {e}")
            continue
        merged = (completed.stdout or "") + "\n" + (completed.stderr or "")
        parsed = parse_meshtastic_position_output(merged)
        if not parsed:
            print(f"No position line from CLI for {node}; meshtastic exit {completed.returncode}")
            continue
        print(
            f"Requested {node} (hardware_number={hw_num}); CLI saw "
            f"({parsed['latitude']:.6f}, {parsed['longitude']:.6f}) — "
            f"await MQTT JSON position uplink for persistence"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
