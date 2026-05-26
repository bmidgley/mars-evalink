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
import time
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


def _normalize_topic_root(topic: str) -> str:
    """Match evalink mqtt subscriber topic layout (no leading/trailing slashes)."""
    return topic.strip().strip("/")


def _aircraft_topic(topic_root: str, hex_code: str) -> str:
    return f"{topic_root}/aircraft/{hex_code}"


def _env_or_cli(env_name: str, cli_value: str | None) -> tuple[str, str | None]:
    """Prefer dotenv/environment over CLI; return (value, ignored_cli_value_or_none)."""
    env_val = (_env(env_name) or "").strip()
    cli_val = (cli_value or "").strip()
    if env_val:
        ignored = cli_val if cli_val and cli_val != env_val else None
        return env_val, ignored
    return cli_val, None


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


def _normalize_serial_port(port: str) -> str:
    """On macOS, use /dev/cu.* for host-initiated reads (not /dev/tty.*)."""
    if sys.platform != "darwin" or "/dev/tty." not in port:
        return port
    cu = port.replace("/dev/tty.", "/dev/cu.", 1)
    if Path(cu).exists():
        return cu
    return port


def _open_serial(port: str, baud: int):
    """Open serial without toggling DTR/RTS (avoids ESP32 reset on connect)."""
    import serial as _serial

    ser = _serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 1
    ser.dsrdtr = False
    ser.rtscts = False
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Listen to RemoteID serial and publish to MQTT")
    p.add_argument(
        "--port",
        dest="port",
        default=None,
        help="Serial port path (only used if REMOTEID_PORT is not set in .env / environment)",
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
        help="MQTT topic root (only used if MQTT_TOPIC is not set in .env / environment)",
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
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Log non-JSON serial lines and skipped JSON (for debugging)",
    )
    return p.parse_args()


def main() -> int:
    # Load repo-root .env (this script lives in the repo root).
    repo_root = Path(__file__).resolve().parent
    load_dotenv(dotenv_path=repo_root / ".env")

    args = parse_args()

    env_port = (_env("REMOTEID_PORT") or "").strip()
    cli_port = (args.port or "").strip()
    port = env_port or cli_port
    if env_port and cli_port and env_port != cli_port:
        print(
            f"Using REMOTEID_PORT={env_port} from environment (--port {cli_port} ignored)",
            file=sys.stderr,
        )
    baud = args.baud
    if baud is None:
        baud = int(_env("REMOTEID_BAUD", "115200"))

    topic_root, ignored_topic = _env_or_cli("MQTT_TOPIC", args.topic_root)
    topic_root = _normalize_topic_root(topic_root)
    if ignored_topic:
        print(
            f'Using MQTT_TOPIC={topic_root!r} from environment (--topic-root {ignored_topic!r} ignored)',
            file=sys.stderr,
        )

    mqtt_server, ignored_server = _env_or_cli("MQTT_SERVER", args.mqtt_server)
    if ignored_server:
        print(
            f"Using MQTT_SERVER={mqtt_server!r} from environment (--mqtt-server ignored)",
            file=sys.stderr,
        )

    env_port = _env("MQTT_PORT")
    if env_port:
        mqtt_port = int(env_port.strip())
        if args.mqtt_port is not None and args.mqtt_port != mqtt_port:
            print(
                f"Using MQTT_PORT={mqtt_port} from environment (--mqtt-port ignored)",
                file=sys.stderr,
            )
    else:
        mqtt_port = args.mqtt_port or 1883

    env_keepalive = _env("MQTT_KEEPALIVE")
    if env_keepalive:
        mqtt_keepalive = int(env_keepalive.strip())
    else:
        mqtt_keepalive = args.mqtt_keepalive or 60

    env_user = _env("MQTT_USER")
    if env_user is not None:
        mqtt_user = env_user
        if args.mqtt_user is not None and args.mqtt_user != env_user:
            print("Using MQTT_USER from environment (--mqtt-user ignored)", file=sys.stderr)
    else:
        mqtt_user = args.mqtt_user

    env_password = _env("MQTT_PASSWORD")
    if env_password is not None:
        mqtt_password = env_password
    else:
        mqtt_password = args.mqtt_password

    if args.mqtt_tls is not None:
        mqtt_tls = bool(args.mqtt_tls)
    else:
        mqtt_tls = _env_truthy("MQTT_TLS")

    if not port:
        print("ERROR: Set REMOTEID_PORT or pass --port.", file=sys.stderr)
        return 2

    raw_port = port
    port = _normalize_serial_port(port)
    if port != raw_port:
        print(f"Using {port} (macOS call-out device; {raw_port} often receives no data)")
    if not topic_root:
        print("ERROR: Set MQTT_TOPIC in .env / environment or pass --topic-root.", file=sys.stderr)
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
    publish_pattern = _aircraft_topic(topic_root, "<hex>")
    print(f"MQTT topic prefix from MQTT_TOPIC: {topic_root!r}")
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

    for _ in range(50):
        if client.is_connected():
            break
        time.sleep(0.1)
    if not client.is_connected():
        print("ERROR: MQTT broker did not acknowledge connection in time.", file=sys.stderr)
        client.loop_stop()
        return 1
    print(f"MQTT connected; will publish to {publish_pattern}")

    print(f"Listening for RemoteID on {port} @ {baud}")

    verbose = args.verbose

    try:
        ser = _open_serial(port, baud)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open serial port {port}: {e!r}", file=sys.stderr)
        return 1

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            # Firmware emits debug lines; README says only JSON lines start with "{"
            if not line.lstrip().startswith("{"):
                if verbose:
                    print(f"[serial] {line}", flush=True)
                continue
            if line.lstrip() != line:
                line = line.lstrip()

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                if verbose:
                    print(f"[skip] bad JSON: {line[:200]}", flush=True)
                continue

            if not isinstance(message, dict):
                if verbose:
                    print(f"[skip] JSON is not an object", flush=True)
                continue

            raw_hex_code = str(message.get("ID") or "").strip()
            if not raw_hex_code:
                if verbose:
                    print(f"[skip] no ID in message", flush=True)
                continue
            if re.fullmatch(r"[0-9A-Fa-f]+", raw_hex_code) is None:
                if verbose:
                    print(f'[skip] invalid ID: "{raw_hex_code}"', flush=True)
                continue

            hex_code = raw_hex_code.upper()
            topic = _aircraft_topic(topic_root, hex_code)

            payload = dict(message)
            payload["source"] = "remoteid"
            client.publish(topic, json.dumps(payload, separators=(",", ":")))

            if verbose:
                lat, lon, alt = _location_from_message(message)
                loc = _format_location(lat, lon, alt)
                print(f"RemoteID {hex_code}: {loc} -> {topic}", flush=True)
            else:
                print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\nStopping RemoteID feed.")
    finally:
        try:
            ser.close()
        except Exception:
            pass
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

