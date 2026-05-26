# mars-evalink

[Slides introducing the use of evalink](https://docs.google.com/presentation/d/1PYlcqHhvzJZOTWwN_vaB-AK0Zji_hNcWag889cMgBhg/edit#slide=id.p)

## Development

Make the erd:

./manage.py graph_models -a -g -o ../docs/schema.png

## Install

```
sudo useradd -m evalink
sudo su - evalink
git clone git@github.com:bmidgley/mars-evalink.git
cd mars-evalink
apt install libgraphviz-dev mosquitto-clients mosquitto postgresql postgresql-client python3 python3-pip certbot nginx python3-certbot-nginx uwsgi uwsgi-plugin-python3
pip install -r requirements.txt
export mpass=xxx
export spass=yyy
sudo mosquitto_passwd -c /etc/mosquitto/passwd meshgateway $mpass

cat > .env <<EOF
HOST=localhost
NAME=evalink
PORT=5432
DBUSER=evalink
PASSWORD=$spass
SSLMODE=require
MQTT_SERVER=localhost
MQTT_PORT=1883
MQTT_KEEPALIVE=60
MQTT_USER=meshgateway
MQTT_PASSWORD=$mpass
MQTT_NODE_NUMBER=3663164608
MQTT_TLS=1
MQTT_KEEPALIVE=60
MQTT_TOPIC="msh/MarsSociety/MDRS"
STATIC_ROOT=/home/evalink/static
MEDIA_ROOT=/home/evalink/media
EOF

cat >/etc/nginx/sites-enabled/default <<EOF
server {
    listen 80;
    server_name 127.0.0.1;

    location = /favicon.ico { access_log off; log_not_found off; }
    location /static {
        autoindex on;
        alias /home/evalink/static;
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
    }
}
EOF

sudo -u postgres createdb evalink
sudo -u postgres createuser evalink
echo "GRANT ALL PRIVILEGES ON DATABASE evalink TO evalink;" | sudo -u postgres psql
echo "GRANT USAGE ON SCHEMA public TO evalink;" | sudo -u postgres psql
echo "GRANT CREATE ON SCHEMA public TO evalink;" | sudo -u postgres psql

cd evalink
./manage.py collectstatic
./manage.py migrate

cat >/etc/systemd/system/evalink.service <<EOF
[Unit]
Description=Gunicorn instance to serve evalink
After=network.target

[Service]
User=evalink
Group=www-data
WorkingDirectory=/home/evalink/mars-evalink/evalink
Environment="PATH=/home/evalink/bin"
Environment="DJANGO_SETTINGS_MODULE=evalink.settings"
ExecStart=/home/evalink/bin/gunicorn evalink.wsgi


[Install]
WantedBy=multi-user.target
EOF

sudo systemctl start evalink
sudo systemctl enable evalink
```

## Docker / ZimaOS

A `docker-compose.yml` is provided for one-shot deployment on ZimaOS (or any
Docker host). It brings up three services on a private bridge network:

| Service | Image                | Exposed?                                         |
|---------|----------------------|--------------------------------------------------|
| `db`    | `postgres:16-alpine` | internal only (no host port)                     |
| `mqtt`  | `eclipse-mosquitto:2`| host port (Cloudflare Spectrum fronts it w/ TLS) |
| `web`   | built from `Dockerfile` | host port (Cloudflare proxies HTTPS to it)    |

Inside the compose network the web app talks to `db:5432` and `mqtt:1883` in
the clear. Cloudflare terminates TLS on both public-facing edges:

- HTTPS web -> Cloudflare proxy / Tunnel -> `web:8000` (plain HTTP).
- MQTT 8883 TLS -> Cloudflare Spectrum -> `mqtt:1883` (plain MQTT).

The Django container also runs the MQTT subscriber thread (started from
`evalink/__init__.py`), so a single `web` container is enough for both
serving HTTP and consuming MQTT.

### First run

```
cp .env.docker.example .env
# edit .env: set POSTGRES_PASSWORD, MQTT_USER/MQTT_PASSWORD,
# DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS

docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

Migrations and `collectstatic` run automatically on container start
(`RUN_MIGRATIONS=1`, `RUN_COLLECTSTATIC=1`). Static files are served by
WhiteNoise from the web container, so no separate nginx is required.

### Cloudflare wiring

- Web: point a Cloudflare-proxied DNS record (orange cloud) at the host's
  public address, or run `cloudflared tunnel` on the host pointing at
  `http://127.0.0.1:${WEB_HOST_PORT}`. Add every hostname Cloudflare
  forwards to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- MQTT: configure a Cloudflare Spectrum app (TCP, TLS, public port 8883)
  with origin `host:${MQTT_HOST_PORT}` (default `1883`), or use a
  `cloudflared` TCP tunnel that targets the same address. Anonymous access
  is disabled in `mosquitto/config/mosquitto.conf`; the broker entrypoint
  generates `/mosquitto/data/passwd` from `MQTT_USER` / `MQTT_PASSWORD` on
  every start, so credential changes take effect on `docker compose up`.

### Useful commands

```
docker compose logs -f web              # tail Django + MQTT subscriber output
docker compose exec web python manage.py shell
docker compose exec db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose restart web              # picks up new .env values
```

## Testing

### Running Tests Locally

To run tests locally, you can use the provided script:

```bash
./run_tests.sh
```

This script will:
- Set up the test environment variables
- Activate the virtual environment
- Install dependencies
- Run all Django tests

### Django Development Menu

For easy access to common Django commands, you can use the interactive menu:

```bash
# Python version (more features)
./menu.py

# Shell version (simpler)
./django_menu.sh
```

The menu provides quick access to:
- 🖥️  Run Development Server (runserver)
- 🧪 Run Tests
- 🗄️  Run Database Migrations
- 📊 Create Database Schema Diagram
- 🧹 Collect Static Files
- 👤 Create Superuser
- 🔍 Django Shell
- 📋 Show Django Commands
- ⚙️  Check Django Configuration

### Running Tests Manually

If you prefer to run tests manually:

```bash
cd evalink
export HOST=localhost
export NAME=test_db
export PORT=5432
export DBUSER=postgres
export PASSWORD=postgres
export SSLMODE=disable
export CAMPUS="Test Campus"
python manage.py test --verbosity=2
```

### GitHub Actions

Tests are automatically run on pull requests and pushes to main/master branches. The GitHub Actions workflow:

1. Sets up a PostgreSQL database service
2. Installs Python dependencies
3. Runs all Django tests
4. Specifically runs the `FeaturesEndpointTestCase` tests

You can view the test results in the "Actions" tab of the GitHub repository.

## Test standalone
```
cd mars-evalink/evalink
DJANGO_SETTINGS_MODULE=evalink.settings gunicorn evalink.wsgi
```

## Radios

Allow radios to be seen on mqtt.

```
meshtastic --ch-set module_settings.position_precision 32 --ch-index 0
```

## RemoteID

Connect an ESP32-S3 to a serial port and flash the RemoteID sketch. The device prints one JSON object per line at 115200 baud. Use `python3 list_serial.py` from the repo root to see which `/dev/ttyACM*` (or `/dev/serial/by-id/...`) path belongs to the board.

An example line from the device:

```
{"ID":"18656A000A46", "lat":0.000000, "long":0.000000, "alt":-1000.0, "iso":"2028-01-15T05:09:52Z", "packet_hex":"B716FAFF0DE1F019070012313836353641303236333000000000000000000000000000225068616E746F6D340000000000000000000000000000000000000000000000000000000000000000000000000000000020300011000000000000000000000000000000000000000000320044726F6E6573204944207465737420666C6967687400000000000000000000000000000000000000000000000000000052000000000000000000000000000000000000000000000000"}
```

The firmware also emits debug lines that are not JSON (they do not start with `{`); the listener ignores those.

### Minimum environment variables

Put these in `.env` at the repo root (or export them). `load_dotenv()` is called when the command runs.

**Required to run `run_remoteid_feed`:**

| Variable | Purpose |
|----------|---------|
| `REMOTEID_PORT` | Serial device path (e.g. `/dev/ttyACM2` or `/dev/serial/by-id/...`). On macOS, prefer `/dev/cu.*` (or let the script rewrite `/dev/tty.*` to `/dev/cu.*`) |
| `MQTT_TOPIC` | MQTT topic root; positions publish to `{MQTT_TOPIC}/aircraft/{hex}` |
| `MQTT_SERVER` | MQTT broker hostname |

**Usually required** (if your broker uses auth or TLS, same values as the main evalink install):

| Variable | Purpose |
|----------|---------|
| `MQTT_PORT` | Broker port (default `1883`) |
| `MQTT_USER` / `MQTT_PASSWORD` | Broker credentials |
| `MQTT_TLS` | Set to any non-empty value to enable TLS |

**Required for drones to appear on the map** (not read by `run_remoteid_feed` itself, but required by evalink when it consumes MQTT):

| Variable | Purpose |
|----------|---------|
| `CAMPUS` | Must match a `Campus` name in the database; RemoteID aircraft are assigned to this campus |
| Database vars | Same `HOST`, `NAME`, `PORT`, `DBUSER`, `PASSWORD`, `SSLMODE` as normal evalink |

Install pyserial once: `pip install pyserial` (not listed in `requirements.txt`).

### Invoke the listener

From the repo root, with evalink already running (gunicorn or `runserver`) so the MQTT subscriber in `evalink/__init__.py` can store aircraft:

```bash
pip install pyserial   # first time only
./run_remoteid_feed.py
```

Optional overrides:

```bash
./run_remoteid_feed.py --port /dev/serial/by-id/usb-...
./run_remoteid_feed.py --baud 115200
./run_remoteid_feed.py --topic-root 'msh/MarsSociety/MDRS'
./run_remoteid_feed.py --verbose
```

Stop with Ctrl+C. You should see `Listening for RemoteID on ...` and `RemoteID <hex>: lat=...` when valid JSON lines arrive. Use `--verbose` to print firmware debug lines and skipped JSON.

On macOS, if the listener is silent but a serial monitor shows data, set `REMOTEID_PORT` to the `/dev/cu.usbmodem*` path (not `/dev/tty.usbmodem*`). The script auto-rewrites `tty` to `cu` when both exist.

Flow: ESP32 serial -> `run_remoteid_feed` -> MQTT `{MQTT_TOPIC}/aircraft/{ID}` -> evalink MQTT handler -> map.