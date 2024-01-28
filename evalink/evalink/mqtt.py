import paho.mqtt.client as mqtt
from dotenv import load_dotenv
import os

def on_connect(client, userdata, flags, rc):
    client.subscribe("msh/+/json/#")

def on_message(client, userdata, msg):
    print(msg.payload)

load_dotenv()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
# client.tls_set()
client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)