"""
Listen to RemoteID serial feed and publish aircraft messages to MQTT.

Usage:
  python manage.py run_remoteid_feed
  python manage.py run_remoteid_feed --port /dev/tty.usbmodem101
"""
import json
import os
import re

from django.core.management.base import BaseCommand
import paho.mqtt.client as mqtt


class Command(BaseCommand):
    help = "Read RemoteID serial messages and publish to MQTT aircraft topic"

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            dest="port",
            default=None,
            help='Serial port path (defaults to REMOTEID_PORT env var)',
        )
        parser.add_argument(
            "--baud",
            dest="baud",
            type=int,
            default=115200,
            help="Serial baud rate (default: 115200)",
        )
        parser.add_argument(
            "--topic-root",
            dest="topic_root",
            default=None,
            help='MQTT topic root (defaults to MQTT_TOPIC env var)',
        )

    def handle(self, *args, **options):
        from dotenv import load_dotenv

        load_dotenv()

        port = (options.get("port") or os.getenv("REMOTEID_PORT") or "").strip()
        baud = int(options.get("baud") or 115200)
        topic_root = (options.get("topic_root") or os.getenv("MQTT_TOPIC") or "").strip()

        if not port:
            self.stderr.write(self.style.ERROR("Set REMOTEID_PORT or pass --port."))
            return
        if not topic_root:
            self.stderr.write(self.style.ERROR("Set MQTT_TOPIC or pass --topic-root."))
            return

        try:
            import serial
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "pyserial is required. Install with: pip install pyserial"
                )
            )
            return

        mqtt_server = (os.getenv("MQTT_SERVER") or "").strip()
        mqtt_port = int((os.getenv("MQTT_PORT") or "1883").strip())
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_password = os.getenv("MQTT_PASSWORD")
        mqtt_tls = bool(os.getenv("MQTT_TLS"))
        mqtt_keepalive = int((os.getenv("MQTT_KEEPALIVE") or "60").strip())

        if not mqtt_server:
            self.stderr.write(self.style.ERROR("Set MQTT_SERVER in environment."))
            return

        client = mqtt.Client()
        if mqtt_tls:
            client.tls_set()
        if mqtt_user or mqtt_password:
            client.username_pw_set(username=mqtt_user, password=mqtt_password)
        client.connect(mqtt_server, mqtt_port, mqtt_keepalive)
        client.loop_start()

        self.stdout.write(f"Listening for RemoteID on {port} @ {baud}")
        self.stdout.write(f'Publishing aircraft messages to "{topic_root}/aircraft/<hex>"')

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
                        self.stderr.write(self.style.WARNING(f"Skipping bad JSON: {line}"))
                        continue

                    if not isinstance(message, dict):
                        continue

                    raw_hex_code = str(message.get("ID") or "").strip()
                    if not raw_hex_code:
                        self.stderr.write(self.style.WARNING("Skipping message with no ID"))
                        continue
                    if re.fullmatch(r"[0-9A-Fa-f]+", raw_hex_code) is None:
                        self.stderr.write(
                            self.style.WARNING(
                                f'Skipping message with invalid ID format: "{raw_hex_code}"'
                            )
                        )
                        continue
                    hex_code = raw_hex_code.upper()
                    topic = f"{topic_root}/aircraft/{hex_code}"
                    payload = dict(message)
                    payload["source"] = "remoteid"
                    client.publish(topic, json.dumps(payload))
                    self.stdout.write(f"Published RemoteID position for {hex_code}")
        except KeyboardInterrupt:
            self.stdout.write("\nStopping RemoteID feed.")
        finally:
            client.loop_stop()
            client.disconnect()
