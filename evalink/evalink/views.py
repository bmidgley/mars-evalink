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
            number = int(os.getenv('MQTT_NODE_NUMBER'))
            send_message = {'channel': 0, 'from': number, 'payload': message, 'type': 'sendtext'}
            tls = None #os.getenv('MQTT_TLS')
            data = json.dumps(send_message)
            topic = "msh/2/json/mqtt/"
            publish.single(topic, data,
                hostname=os.getenv('MQTT_SERVER'),
                port=int(os.getenv('MQTT_PORT')),
                auth = {'username':os.getenv('MQTT_USER'), 'password':os.getenv('MQTT_PASSWORD')},
                tls=tls,
                )

    form = ChatForm()
    return render(request, "chat.html", {"form": form})
