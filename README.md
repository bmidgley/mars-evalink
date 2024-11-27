# mars-evalink

[Slides introducing the use of evalink](https://docs.google.com/presentation/d/1PYlcqHhvzJZOTWwN_vaB-AK0Zji_hNcWag889cMgBhg/edit#slide=id.p)

## Development

Make the erd:

./manage.py graph_models -a -g -o ../docs/schema.png

## Install

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

