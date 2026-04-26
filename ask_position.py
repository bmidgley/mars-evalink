#!/usr/bin/env python3
"""
Standalone script: fetch stalenode JSON from evalink and run
meshtastic --request-position --dest <hardware_node> for each stale station.
Parses "Position received: (lat, lon) Altitudem ..." from meshtastic output
and publishes a JSON position packet on MQTT so evalink treats it like a
normal mesh position uplink (same shape as mqtt.on_message -> handler).

Requires: meshtastic CLI, paho-mqtt, python-dotenv (optional, loads .env).
Env: MQTT_SERVER, MQTT_PORT, MQTT_TOPIC, MQTT_USER, MQTT_PASSWORD, MQTT_TLS
     MQTT_JSON_BRIDGE_SEG (default 2), MQTT_JSON_CHANNEL (default LongFast)
     MESHTASTIC_REQUEST_POSITION_TIMEOUT (seconds, default 180)

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
import time
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


def build_position_bus_message(hardware_number, latitude, longitude, altitude=None):
    """JSON envelope matching evalink mqtt.on_message checks and handler.process_message position branch."""
    ts = int(time.time())
    lat_i = int(round(latitude * 1e7))
    lon_i = int(round(longitude * 1e7))
    payload = {
        "latitude_i": lat_i,
        "longitude_i": lon_i,
        "time": ts,
    }
    if altitude is not None:
        payload["altitude"] = altitude
    return {
        "type": "position",
        "payload": payload,
        "from": int(hardware_number),
        "channel": 0,
        "timestamp": ts,
        "id": int(time.time() * 1_000_000),
    }


def _mqtt_uplink_topic(hardware_node):
    """Topic must match MQTT_TOPIC/+/json/# (see evalink mqtt.on_connect)."""
    load_dotenv()
    root = (os.getenv("MQTT_TOPIC") or "").strip().strip("/")
    if not root:
        raise RuntimeError("MQTT_TOPIC is not set")
    bridge_seg = (os.getenv("MQTT_JSON_BRIDGE_SEG") or "2").strip()
    channel_name = (os.getenv("MQTT_JSON_CHANNEL") or "LongFast").strip()
    node = (hardware_node or "").strip()
    if not node.startswith("!"):
        node = "!" + node
    return f"{root}/{bridge_seg}/json/{channel_name}/{node}"


def publish_position_bus_message(message, hardware_node):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("paho-mqtt is not installed; cannot publish to MQTT")
        return False
    topic = _mqtt_uplink_topic(hardware_node)
    body = json.dumps(message, separators=(",", ":"))
    client = None
    try:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except (AttributeError, TypeError):
            client = mqtt.Client()
        if os.getenv("MQTT_TLS"):
            client.tls_set()
        user = os.getenv("MQTT_USER")
        if user is not None:
            client.username_pw_set(username=user, password=os.getenv("MQTT_PASSWORD") or "")
        host = os.getenv("MQTT_SERVER", "localhost")
        port = int(os.getenv("MQTT_PORT", "1883"))
        client.connect(host, port, int(os.getenv("MQTT_KEEPALIVE", "60")))
        client.publish(topic, body)
        client.disconnect()
    except Exception as e:
        print(f"MQTT publish failed ({topic}): {e}")
        return False
    return True


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
            print(f"No position line parsed for {node}; meshtastic exit {completed.returncode}")
            continue
        msg = build_position_bus_message(
            hw_num,
            parsed["latitude"],
            parsed["longitude"],
            parsed["altitude"],
        )
        if publish_position_bus_message(msg, node):
            print(
                f"Published position for hardware_number={hw_num} "
                f"({parsed['latitude']:.6f}, {parsed['longitude']:.6f})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
