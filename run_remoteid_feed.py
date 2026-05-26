#!/usr/bin/env python3
"""
Standalone RemoteID listener.

Reads an ESP32-S3 RemoteID serial stream and publishes each valid JSON
message to MQTT at:

  {MQTT_TOPIC}/aircraft/<hex>

This duplicates the core functionality of the Django management command
without importing Django (no settings/app side-effects).

Typical usage:
  python3 run_remoteid_feed.py

Or with explicit args:
  python3 run_remoteid_feed.py --port /dev/serial/by-id/... --baud 115200
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_a, **_k):
        return False


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    # Handle values like MQTT_TOPIC="msh/MDRS"
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1].strip()
    return v


def _env_truthy(name: str) -> bool:
    v = os.getenv(name)
    if v is None:
        return False
    v = v.strip().lower()
    return v not in ("", "0", "false", "no", "off")


def _location_from_message(message: dict) -> tuple[float | None, float | None, float | None]:
    """Return (lat, lon, alt) using RemoteID / aircraft field names."""
    lat = message.get("lat", message.get("latitude"))
    lon = message.get("lon", message.get("long", message.get("longitude")))
    alt = message.get("alt", message.get("altitude"))
    try:
        lat = float(lat) if lat is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lon = None
    try:
        alt = float(alt) if alt is not None else None
    except (TypeError, ValueError):
        alt = None
    return lat, lon, alt


def _format_location(lat: float | None, lon: float | None, alt: float | None) -> str:
    if lat is None or lon is None:
        return "location unknown"
    parts = [f"lat={lat:.6f}", f"lon={lon:.6f}"]
    if alt is not None:
        parts.append(f"alt={alt:.1f}m")
    return ", ".join(parts)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Listen to RemoteID serial and publish to MQTT")
    p.add_argument(
        "--port",
        dest="port",
        default=None,
        help="Serial port path (defaults to REMOTEID_PORT env var)",
    )
    p.add_argument(
        "--baud",
        dest="baud",
        type=int,
        default=None,
        help="Serial baud rate (default: 115200 or REMOTEID_BAUD if set)",
    )
    p.add_argument(
        "--topic-root",
        dest="topic_root",
        default=None,
        help="MQTT topic root (defaults to MQTT_TOPIC env var)",
    )

    p.add_argument(
        "--mqtt-server",
        dest="mqtt_server",
        default=None,
        help="MQTT broker hostname (defaults to MQTT_SERVER env var)",
    )
    p.add_argument(
        "--mqtt-port",
        dest="mqtt_port",
        type=int,
        default=None,
        help="MQTT broker port (defaults to MQTT_PORT or 1883)",
    )
    p.add_argument(
        "--mqtt-keepalive",
        dest="mqtt_keepalive",
        type=int,
        default=None,
        help="MQTT keepalive seconds (defaults to MQTT_KEEPALIVE or 60)",
    )
    p.add_argument(
        "--mqtt-user",
        dest="mqtt_user",
        default=None,
        help="MQTT username (defaults to MQTT_USER env var)",
    )
    p.add_argument(
        "--mqtt-password",
        dest="mqtt_password",
        default=None,
        help="MQTT password (defaults to MQTT_PASSWORD env var)",
    )
    p.add_argument(
        "--mqtt-tls",
        dest="mqtt_tls",
        default=None,
        help="Enable MQTT TLS (overrides MQTT_TLS env var); any non-empty value enables it",
    )
    return p.parse_args()


def main() -> int:
    # Load repo-root .env (this script lives in the repo root).
    repo_root = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=repo_root / ".env")

    args = parse_args()

    port = (args.port or _env("REMOTEID_PORT") or "").strip()
    baud = args.baud
    if baud is None:
        baud = int(_env("REMOTEID_BAUD", "115200"))

    topic_root = (args.topic_root or _env("MQTT_TOPIC") or "").strip()
    mqtt_server = (args.mqtt_server or _env("MQTT_SERVER") or "").strip()
    mqtt_port = args.mqtt_port or int(_env("MQTT_PORT", "1883"))
    mqtt_keepalive = args.mqtt_keepalive or int(_env("MQTT_KEEPALIVE", "60"))
    mqtt_user = args.mqtt_user if args.mqtt_user is not None else _env("MQTT_USER")
    mqtt_password = (
        args.mqtt_password if args.mqtt_password is not None else _env("MQTT_PASSWORD")
    )

    if args.mqtt_tls is not None:
        mqtt_tls = bool(args.mqtt_tls)
    else:
        mqtt_tls = _env_truthy("MQTT_TLS")

    if not port:
        print("ERROR: Set REMOTEID_PORT or pass --port.", file=sys.stderr)
        return 2
    if not topic_root:
        print("ERROR: Set MQTT_TOPIC or pass --topic-root.", file=sys.stderr)
        return 2
    if not mqtt_server:
        print("ERROR: Set MQTT_SERVER in environment.", file=sys.stderr)
        return 2

    try:
        import serial  # pyserial
    except ImportError:
        print("ERROR: pyserial is required. Install with: pip install pyserial", file=sys.stderr)
        return 2

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("ERROR: paho-mqtt is required. Install with: pip install paho-mqtt", file=sys.stderr)
        return 2

    # Import-time networking is avoided; we connect only after env/args validation.
    print(f"Connecting to MQTT {mqtt_server}:{mqtt_port} (TLS enabled: {mqtt_tls})")
    client = mqtt.Client()
    if mqtt_tls:
        client.tls_set()
    if mqtt_user or mqtt_password:
        client.username_pw_set(username=mqtt_user, password=mqtt_password)

    try:
        client.connect(mqtt_server, mqtt_port, mqtt_keepalive)
    except Exception as e:
        print(f"ERROR: MQTT connect failed: {e!r}", file=sys.stderr)
        return 1

    client.loop_start()

    print(f"Listening for RemoteID on {port} @ {baud}")
    print(f'Publishing aircraft messages to "{topic_root}/aircraft/<hex>"')

    try:
        with serial.Serial(port=port, baudrate=baud, timeout=1) as ser:
            while True:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                # Firmware emits debug lines; README says only JSON lines start with "{"
                if not line.startswith("{"):
                    continue

                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    # Skip bad JSON without spamming.
                    continue

                if not isinstance(message, dict):
                    continue

                raw_hex_code = str(message.get("ID") or "").strip()
                if not raw_hex_code:
                    continue
                if re.fullmatch(r"[0-9A-Fa-f]+", raw_hex_code) is None:
                    continue

                hex_code = raw_hex_code.upper()
                topic = f"{topic_root}/aircraft/{hex_code}"

                payload = dict(message)
                payload["source"] = "remoteid"
                client.publish(topic, json.dumps(payload, separators=(",", ":")))

                lat, lon, alt = _location_from_message(message)
                loc = _format_location(lat, lon, alt)
                print(f"RemoteID {hex_code}: {loc} -> {topic}")
    except KeyboardInterrupt:
        print("\nStopping RemoteID feed.")
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

