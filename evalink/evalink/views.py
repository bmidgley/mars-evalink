from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from evalink.models import *
from datetime import date, timedelta, datetime
from django.shortcuts import render
from dotenv import load_dotenv
from .forms import ChatForm
import paho.mqtt.publish as publish
import os
import json

load_dotenv()

@login_required
def features(request):
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    past = date.today() - timedelta(days = 1)
    for station in Station.objects.filter(updated_at__gt = past).order_by('id').all():
        if station.features and 'geometry' in station.features and 'coordinates' in station.features['geometry']:
            data["features"].append(station.features)
    return JsonResponse(data, json_dumps_params={'indent': 2})

@login_required
def chat(request):
    if request.method == "POST":
        form = ChatForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data['message']
            user = request.user
            number = 1000000000 + user.id
            hexid = '!' + hex(number)[2:10]
            email = user.email
            timestamp = int(datetime.timestamp(datetime.now()))
            node_message = {'channel': 0, 'from': number, 'id': timestamp + 1, 'payload': {'hardware': 777, 'id': hexid, 'longname': email, 'shortname': email[0:3]}, 'sender': hexid, 'timestamp': timestamp, 'to': number, 'type': 'nodeinfo'}
            text_message = {'channel': 0, 'from': number, 'id': timestamp + 2, 'payload': {'text': message}, 'sender': hexid, 'timestamp': timestamp, 'to': number, 'type': 'text'}
            send_message = {'channel': 0, 'from': number, 'id': timestamp + 3, 'payload': message, 'sender': hexid, 'timestamp': timestamp, 'type': 'sendtext'}
            broadcast(node_message, "LongFast")
            broadcast(text_message, "LongFast")
            broadcast(send_message, 0)
            # {'channel': 0, 'from': 4054905683, 'id': 1508002140, 'payload': {'text': 'Test7'}, 'rssi': -78, 'sender': '!a3fb58c4', 'snr': 12.25, 'timestamp': 170 797 4647, 'to': 4294967295, 'type': 'text'}

    form = ChatForm()
    return render(request, "chat.html", {"form": form})

def broadcast(map, sub):
    tls = None #os.getenv('MQTT_TLS')
    print(map)
    data = json.dumps(map)
    # msh/2/json/CHANNELID/NODEID
    topic = f"msh/2/json/{sub}/{map['sender']}"
    print(f'{topic} => {data}')
    publish.single(topic, data,
        hostname=os.getenv('MQTT_SERVER'),
        port=int(os.getenv('MQTT_PORT')),
        auth = {'username':os.getenv('MQTT_USER'), 'password':os.getenv('MQTT_PASSWORD')},
        tls=tls,
        )
