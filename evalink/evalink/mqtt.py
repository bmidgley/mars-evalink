import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os
import json
from . import handler

def on_connect(client, _userdata, _flags, _rc):
    client.subscribe("msh/+/json/#")

def on_disconnect(_client, _userdata, _rc):
    # print("on_disconnect?")
    pass

def on_message(_client, _userdata, msg):
    message = json.loads(msg.payload)
    if not verify(message, 'type'): return
    if not verify(message, 'payload'): return
    if not verify(message, 'timestamp'): return
    if not verify(message, 'from'): return
    handler.process_message(message)

def verify(message, field):
    if field not in message: print(f'reject {message} for missing {field}')
    return field in message

load_dotenv()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect
if os.getenv('MQTT_TLS'): client.tls_set()
client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)