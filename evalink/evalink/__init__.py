from . import mqtt

if mqtt.client is not None:
    mqtt.client.loop_start()