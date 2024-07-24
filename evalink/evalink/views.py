from django.http import JsonResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from evalink.models import *
from datetime import date, timedelta, datetime
from django.utils.dateparse import parse_date
from django.shortcuts import render
from dotenv import load_dotenv
from .forms import ChatForm
import paho.mqtt.client as mqtt
import os
import json
import zoneinfo
from . import handler

load_dotenv()

@login_required
def index(request):
    return render(request, "map.html")

@login_required
def features(request):
    data = {
        "type": "FeatureCollection",
        "features": [],
    }
    past = date.today() - timedelta(days = 90)
    for station in Station.objects.filter(updated_at__gt = past).order_by('name').all():
        if station.features and 'geometry' in station.features and 'coordinates' in station.features['geometry']:
            station.features['properties']['hardware_number'] = station.hardware_number
            station.features['properties']['hardware_node'] = station.hardware_node
            station.features['properties']['id'] = station.id
            data["features"].append(station.features)
    return JsonResponse(data, json_dumps_params={'indent': 2})

@login_required
def texts(request):
    text_messages = TextLog.objects.all().order_by('-updated_at')[:100:-1]
    return JsonResponse([text_message.serialize() for text_message in text_messages], safe=False, json_dumps_params={'indent': 2})

@login_required
def path(request):
    id = request.GET.get('id')
    station = Station.objects.filter(id=id).first()
    if station == None: return HttpResponseNotFound("not found")
    before_date = localdate(request.GET.get('before_date'), date.today() + timedelta(days = 1))
    after_date = localdate(request.GET.get('after_date'), None)
    result = {'id': station.id, 'name': station.name, 'date': None, 'waypoints': [], 'points': []}
    if after_date:
        position_log = PositionLog.objects.filter(station=station,updated_at__date__gt=after_date).order_by('updated_at').first()
    else:
        position_log = PositionLog.objects.filter(station=station,updated_at__date__lt=before_date).order_by('-updated_at').first()
    if position_log:
        found_date = position_log.updated_at.astimezone(timezone.get_current_timezone()).date()
        result['date'] = found_date
        position_logs = PositionLog.objects.filter(station=station, updated_at__date=found_date).order_by('updated_at').all()
        for log in position_logs:
            result['points'].append({'latitude': log.latitude, 'longitude': log.longitude, 'altitude': log.altitude, 'updated_at': log.updated_at})
        text_logs = TextLog.objects.filter(station=station, updated_at__date=found_date).order_by('updated_at').all()
        for text in text_logs:
            if text.position_log:
                result['waypoints'].append({'latitude': text.position_log.latitude, 'longitude': text.position_log.longitude, 'altitude': text.position_log.altitude, 'updated_at': text.updated_at, 'text': text.text})
    else:
        result['date'] = before_date.date()
    return JsonResponse(result, json_dumps_params={'indent': 2})

def localdate(my_date, default):
    if my_date == None: return default
    if isinstance(my_date, str): my_date = parse_date(my_date)
    my_naive_datetime = datetime.combine(my_date, datetime.min.time())
    tz = timezone.get_current_timezone()
    my_aware_datetime = timezone.make_aware(my_naive_datetime, timezone=tz)
    return my_aware_datetime

@login_required
def chat(request):
    gateway_node_number = int(os.getenv('MQTT_NODE_NUMBER'))

    message = request.GET.get('message')
    if message:
        message = request.user.username + ': ' + message
        send_message = {'channel': 0, 'from': gateway_node_number, 'payload': message, 'type': 'sendtext'}
        data = json.dumps(send_message)
        topic = f'{os.getenv("MQTT_TOPIC")}/2/json/mqtt/'
        client = mqtt.Client()
        if os.getenv('MQTT_TLS'): client.tls_set()
        client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
        client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)
        client.publish(topic, data)
        print("\n", topic, data)
        client.disconnect()
        return JsonResponse({"sent": "ok"}, json_dumps_params={'indent': 2})

    if request.method == "POST":
        form = ChatForm(request.POST)
        if form.is_valid():
            message = request.user.username + ': '
            message += form.cleaned_data['message']
            send_message = {'channel': 0, 'from': gateway_node_number, 'payload': message, 'type': 'sendtext'}
            data = json.dumps(send_message)
            topic = f'{os.getenv("MQTT_TOPIC")}/2/json/mqtt/'
            client = mqtt.Client()
            if os.getenv('MQTT_TLS'): client.tls_set()
            client.username_pw_set(username=os.getenv('MQTT_USER'), password=os.getenv('MQTT_PASSWORD'))
            client.connect(os.getenv('MQTT_SERVER'), int(os.getenv('MQTT_PORT')), 60)
            client.publish(topic, data)
            client.disconnect()
            # do not process the message now or it will appear as a duplicate when it's seen on the network
            # timestamp = int(datetime.timestamp(datetime.now()))
            # text_message = {'channel': 0, 'from': gateway_node_number, 'id': timestamp, 'payload': {'text': message}, 'timestamp': timestamp, 'type': 'text'}
            # handler.process_message(text_message)

    form = ChatForm()
    texts = TextLog.objects.all().order_by('-updated_at')[:20:1]
    return render(request, "chat.html", {"form": form, "texts": texts, "name": request.user.username})
