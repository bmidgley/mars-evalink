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
            send_message = {'channel': 0, 'from': 2751158468, 'payload': message, 'type': 'sendtext'}
            broadcast(node_message, f"LongFast/{hexid}")
            broadcast(text_message, f"LongFast/{hexid}")
            broadcast(send_message, "mqtt")

    form = ChatForm()
    return render(request, "chat.html", {"form": form})

def broadcast(map, sub):
    tls = None #os.getenv('MQTT_TLS')
    data = json.dumps(map)
    topic = f"msh/2/json/{sub}/"
    print(f'{topic} => {data}')
    publish.single(topic, data,
        hostname=os.getenv('MQTT_SERVER'),
        port=int(os.getenv('MQTT_PORT')),
        auth = {'username':os.getenv('MQTT_USER'), 'password':os.getenv('MQTT_PASSWORD')},
        tls=tls,
        )
