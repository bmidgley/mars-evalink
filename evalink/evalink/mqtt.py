import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os
import json
from . import handler

def on_connect(client, _userdata, _flags, _rc):
    client.subscribe("msh/+/json/#")

def on_message(_client, _userdata, msg):
    message = json.loads(msg.payload)
    if 'type' not in message: return
    if 'payload' not in message: return
    if 'timestamp' not in message: return
    if 'from' not in message: return
    handler.process_message(message)

load_dotenv()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
if os.getenv('MQTT_TLS'): client.tls_set()
client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)