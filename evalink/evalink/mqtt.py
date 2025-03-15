import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from django import db
import time
import os
import json
from . import handler
import traceback

def on_connect(client, _userdata, _flags, _rc):
    client.subscribe(f'{os.getenv("MQTT_TOPIC")}/+/json/#')

def on_disconnect(client, _userdata, _rc):
    print("on_disconnect?")

def on_message(_client, _userdata, msg):
    message = json.loads(msg.payload)
    if not verify(message, 'type'): return
    if not verify(message, 'payload'): return
    if not verify(message, 'timestamp'): return
    if not verify(message, 'from'): return
    try:
        handler.process_message(message)
    except Exception as error:
        print(f'handler failed to process {message}: {error} {traceback.print_tb(error.__traceback__)}')
        db.close_old_connections()
        time.sleep(1)

def verify(message, field):
    return field in message

load_dotenv()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
if os.getenv('MQTT_TLS'): client.tls_set()
client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)